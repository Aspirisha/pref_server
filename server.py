import os, os.path
import random
import sqlite3
import string
import time
import json
import pycurl
import re

import util
import cherrypy

DB_STRING = "pref.db"
SERVER_KEY = "AIzaSyAhL2EX96bgmKQSgvwKCrCZjTAwsGzrHNM"
MIN_PASSWORD_LENGTH = 5
MIN_NAME_LENGTH = 3
START_COINS = 100


class StringGeneratorWebService(object):
    exposed = True
    no_auth_requests = ['register', 'ping']
    no_auth_notifications = ['keep_alive']

    @cherrypy.tools.accept(media='text/plain')
    def GET(self):
        return 'Ololo, get request!'

    def POST(self, *args, **kwargs):
        print('kwargs are ' + str(kwargs))

        length = 8
        some_string = ''.join(random.sample(string.hexdigits, int(length)))
        request_type = kwargs['request_type']
        if 'id' in kwargs.keys():
            kwargs['id'] = int(kwargs['id'])

        if request_type == 'request':
            if kwargs['request'] not in StringGeneratorWebService.no_auth_requests:
                if not authentificate_user(**kwargs):
                    return 'failed_to_authorize'
        else:
            if kwargs['notification'] not in StringGeneratorWebService.no_auth_notifications:
                if not authentificate_user(**kwargs):
                    return 'failed_to_authorize'

        process_request(**kwargs) if request_type == 'request' else process_notification(**kwargs)

        return some_string

    def PUT(self, another_string):
        cherrypy.session['mystring'] = another_string

    def DELETE(self):
        cherrypy.session.pop('mystring', None)


class RoomInfo:
    def __init__(self, row, players_number):
        self.id = row['id']
        self.name = row['name']
        self.bullet = row['bullet']
        self.whistCost = row['whist_cost']
        self.gameType = row['game_type']
        self.raspExit = [int(x) for x in row['rasp_exit'].split(' ')]
        self.raspProgression = [int(x) for x in row['rasp_progression'].split(' ')]
        self.withoutThree = True if row['without_three'] == 1 else False
        self.noWhistRaspasyExit = True if row['no_whist_raspasy_exit'] == 1 else False
        self.stalingrad = True if row['stalingrad'] == 1 else False
        self.tenWhist = True if row['ten_whist'] == 1 else False
        self.hasPassword = True if len(row['password']) > 0 else False
        self.playersNumber = players_number


class MyEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__


def send_data(reg_ids, message_data):
    encoder = MyEncoder()
    headers = ["Content-Type:application/json", "Authorization:key=" + SERVER_KEY]
    data = {'data': message_data, 'registration_ids': reg_ids}
    c = pycurl.Curl()
    c.setopt(pycurl.URL, "https://android.googleapis.com/gcm/send")
    c.setopt(pycurl.POST, True)
    c.setopt(pycurl.HTTPHEADER, headers)
    c.setopt(pycurl.POSTFIELDS, encoder.encode(data))
    c.perform()

    c.close()


def process_request(**kwargs):
    globals()['on_' + kwargs['request'] + '_request'](**kwargs)


def process_notification(**kwargs):
    globals()['on_' + kwargs['notification'] + '_notification'](**kwargs)


def on_keep_alive_notification(**kwargs):
    message = time.time()
    try:
        reg_id = kwargs['reg_id'] if 'reg_id' in kwargs.keys() else \
            get_player_row(kwargs['id'], kwargs['password'])['reg_id']
        send_message(reg_id, message, 'KEEP_ALIVE', 0)
    except Exception as e:
        print(e)


def get_player_row(id, password):
    with sqlite3.connect(DB_STRING) as con:
        con.row_factory = sqlite3.Row
        result = con.execute("SELECT * FROM players WHERE id=? AND password=?",
                             (id, password))
        if result.rowcount == 0:
            return None
        return result.fetchone()


def authentificate_user(**kwargs):
    if 'password' not in kwargs.keys():
        return False

    with sqlite3.connect(DB_STRING) as con:
        con.row_factory = sqlite3.Row
        if 'id' in kwargs.keys():
            result = con.execute("SELECT * FROM players WHERE id=? AND password=?",
                                (int(kwargs['id']), kwargs['password']))
        else:
            result = con.execute("SELECT * FROM players WHERE name=? AND password=?",
                                (kwargs['login'], kwargs['password']))
        for row in result:
            id_to_regid[row['id']] = row['reg_id']
            return True
    return False


def on_register_request(**kwargs):
    name = kwargs['login']
    password = kwargs['password']
    reg_id = kwargs['reg_id']

    if not re.match('^[a-zA-Z][a-zA-Z_0-9]*$', name):
        send_message(kwargs['reg_id'], "Name should start with latin letter",
                     'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')
        return

    if len(name) < 3:
        send_message(kwargs['reg_id'], "Name should be at least 3 characters long",
                     'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')
        return

    if len(password) < MIN_PASSWORD_LENGTH:
        send_message(kwargs['reg_id'], "Password should be at least "
                                       "{} characters long".format(MIN_PASSWORD_LENGTH),
                     'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')
        return

    with sqlite3.connect(DB_STRING) as con:
        result = con.execute("SELECT * FROM players WHERE name=?", (name,))

        for row in result:
            send_message(kwargs['reg_id'], "Name already exists",
                         'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')
            return
        cursor = con.execute("INSERT INTO players (name, password, coins, online, reg_id) VALUES(?, ?, ?, ?, ?)",
                             (name, password, START_COINS, True, reg_id))
        data = '{} {} {}'.format(cursor.lastrowid, name, password)
        id_to_regid[cursor.lastrowid] = reg_id
        send_message(reg_id, data, 'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')

        cherrypy.log("Registered player with name={} and password={}".format(name, password))


def on_ping_request(**kwargs):
    send_message(kwargs['reg_id'], "", 'PING_ANSWER', 'KEEP_ALIVE_ANSWER')


def on_signin_request(**kwargs):
    with sqlite3.connect(DB_STRING) as con:
        con.row_factory = sqlite3.Row
        result = con.execute("SELECT * FROM players WHERE name=? AND password=?",
                             (kwargs['login'], kwargs['password']))
        try:
            row = result.fetchone()
            data = '{} {} {}'.format(row['id'], kwargs['login'], kwargs['password'])
            id_to_regid[row['id']] = kwargs['reg_id']
            send_message(kwargs['reg_id'], data, 'ENTRY_ACTIVITY', 'ENTRY_LOGIN_RESULT')
            con.execute("UPDATE players SET online=1, reg_id=? WHERE name=? AND password=?",
                        (kwargs['reg_id'], kwargs['login'], kwargs['password']))
        except TypeError:
            send_message(kwargs['reg_id'], "User not found!",
                         'ENTRY_ACTIVITY', 'ENTRY_LOGIN_RESULT')


def on_existing_rooms_request(**kwargs):
    ret_val = []
    with sqlite3.connect(DB_STRING) as con:
        con.row_factory = sqlite3.Row
        result = con.execute("SELECT * FROM rooms")
        for row in result:
            id = row['id']
            players = con.execute("SELECT * FROM players WHERE room_id=?", (id,))
            players_number = 0
            for p in players:
                players_number += 1
            ret_val.append(RoomInfo(row, players_number))

    data = json.dumps(ret_val, cls=MyEncoder)
    print(data)
    send_message(id_to_regid[kwargs['id']], data, 'ROOMS_ACTIVITY', 'ROOMS_EXISTING_ROOMS')


def on_quit_notification(**kwargs):
    with sqlite3.connect(DB_STRING) as con:
        con.execute("UPDATE players SET online=0 WHERE id=? AND password=?",
                    (kwargs['id'], kwargs['password']))


def on_online_notification(**kwargs):
    with sqlite3.connect(DB_STRING) as con:
        con.execute("UPDATE players SET online=1, reg_id=? WHERE name=? AND password=?",
                    (kwargs['reg_id'], kwargs['login'], kwargs['password']))


def on_my_money_request(**kwargs):
    if not authentificate_user(**kwargs):
        return
    with sqlite3.connect(DB_STRING) as con:
        con.row_factory = sqlite3.Row
        result = con.execute("SELECT coins FROM players WHERE id=?", (kwargs['id'], ))
        coins = result.fetchone()['coins']
        send_message(id_to_regid[kwargs['id']], coins, 'NEW_ROOM_ACTIVITY', 'NEW_ROOM_MONEY')


def on_create_new_room_request(**kwargs):
    with sqlite3.connect(DB_STRING) as con:
        cursor = con.execute("INSERT INTO rooms (name, password, whist_cost, bullet, "
                             "rasp_exit, rasp_progression, without_three, no_whist_raspasy_exit,"
                             "stalingrad, ten_whist, game_type, player1) VALUES(?, ?, ?, ?, ?,"
                             "?, ?, ?, ?, ?, ?, ?)", ("room1", "", kwargs['whist_cost'],
                                                   kwargs['bullet'], "6 7 7", "2 2 2",
                                                   1, 1, kwargs['stalingrad'], 1, kwargs['game_type'],
                                                      kwargs['id']))
        data = '{} {}'.format(0, cursor.lastrowid)
        send_message(id_to_regid[kwargs['id']], data, 'NEW_ROOM_ACTIVITY', 'ROOMS_NEW_ROOM_CREATION_RESULT')


def on_connect_to_existing_request(**kwargs):
    with sqlite3.connect(DB_STRING) as con:
        con.row_factory = sqlite3.Row
        cursor = con.execute('SELECT * FROM rooms WHERE id=?', (kwargs['room_id'], ))
        row = cursor.fetchone()
        if row is None:
            result = '{} {} {}'.format(2, 0, 0)
        else:
            for i in range(1, 4):
                if row['player{}'.format(i)] is None:
                    res = con.execute('UPDATE rooms SET player{}=? WHERE id=?'.format(i),
                                         (kwargs['id'], kwargs['room_id'], ))
                    res = con.execute('UPDATE players SET room_id=?, own_number=? WHERE id=?',
                                         (kwargs['room_id'], i, kwargs['id']))
                    result = '{} {} {}'.format(0, kwargs['room_id'], i)
                    break
            else:
                 result = '{} {} {}'.format(1, 0, 0)

        print(result)
        send_message(id_to_regid[kwargs['id']], result, 'ROOMS_ACTIVITY', 'ROOMS_CONNECTION_RESULT')


def on_all_data_about_room_request(**kwargs):
    with sqlite3.connect(DB_STRING) as con:
        con.row_factory = sqlite3.Row
        cursor = con.execute('SELECT * FROM rooms WHERE id=?', (kwargs['room_id'], ))
        row_room = cursor.fetchone()
        for k in row_room:
            print('{}'.format(k))

        players_number = 0
        players = []
        player_names = []
        for i in range(1, 4):
            k = 'player{}'.format(i)

            if row_room[k] is not None:
                players.append(row_room[k])
                players_number += 1
                cursor = con.execute('SELECT * FROM players WHERE id=?', (row_room[k], ))
                row_player = cursor.fetchone()
                player_names.append(row_player['name'])
            else:
                player_names.append('null')
                players.append('null')
        data = '{} {} {} {} {} {} {}'.format(row_room['name'], players_number, players[0],
                                             players[1], players[2], player_names[0], player_names[1],
                                             player_names[2], row_room['game_type'], )
        send_message(id_to_regid[kwargs['id']], data, 'GAME_ACTIVITY', 'GAME_ROOM_INFO')



def send_message(reg_ids, message, receiver, msg_type):
    if not type(reg_ids) is list:
        reg_ids = [reg_ids]
    message_data = {'message': message, 'receiver': receiver, "messageType": msg_type}
    send_data(reg_ids, message_data)


def setup_database():
    players_table_sql = "CREATE TABLE if NOT EXISTS players (id INTEGER PRIMARY KEY ASC, " \
                        "name VARCHAR(40), password VARCHAR(40), coins UNSIGNED INTEGER," \
                        "room_id INTEGER, reg_id TEXT, own_number INTEGER, online INTEGER, " \
                        "time_left INTEGER, FOREIGN KEY(room_id) REFERENCES rooms(id))"
    rooms_table_sql = "CREATE TABLE if NOT EXISTS rooms (id INTEGER PRIMARY KEY ASC, " \
                      "name VARCHAR(40), password VARCHAR(40), whist_cost INTEGER, bullet INTEGER," \
                      "rasp_exit VARCHAR(10), rasp_progression VARCHAR(10), without_three INTEGER, " \
                      "no_whist_raspasy_exit INTEGER, player1 INTEGER, player2 INTEGER, player3 INTEGER," \
                      " stalingrad INTEGER, ten_whist INTEGER," \
                      "game_type VARCHAR(20))"
    with sqlite3.connect(DB_STRING) as con:
        con.execute(rooms_table_sql)
        con.execute(players_table_sql)


if __name__ == '__main__':
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'text/plain')],
        }
    }

    id_to_regid = {}
    cherrypy.server.socket_host = '0.0.0.0'  # local computer, public available
    cherrypy.engine.subscribe('start', setup_database)
    cherrypy.quickstart(StringGeneratorWebService(), '/', conf)
