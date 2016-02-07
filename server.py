import os, os.path
import random
import sqlite3
import string
import time
import json
import pycurl
import re

import cherrypy

DB_STRING = "pref.db"
SERVER_KEY = "AIzaSyAhL2EX96bgmKQSgvwKCrCZjTAwsGzrHNM"
MIN_PASSWORD_LENGTH = 5
MIN_NAME_LENGTH = 3
START_COINS = 100

class StringGeneratorWebService(object):
    exposed = True

    @cherrypy.tools.accept(media='text/plain')
    def GET(self):
        return 'Ololo, get request!'

    def POST(self, *args, **kwargs):
        print('args are ' + str(args))
        print('kwargs are ' + str(kwargs))

        length = 8
        some_string = ''.join(random.sample(string.hexdigits, int(length)))
        request_type = kwargs['request_type']
        process_request(**kwargs) if request_type == 'request' else process_notification(**kwargs)

        return some_string

    def PUT(self, another_string):
        cherrypy.session['mystring'] = another_string

    def DELETE(self):
        cherrypy.session.pop('mystring', None)


def send_data(reg_ids, message_data):
    encoder = json.JSONEncoder()
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
    globals()['on_'+kwargs['request']+'_request'](**kwargs)


def process_notification(**kwargs):
    globals()['on_'+kwargs['notification']+'_notification'](**kwargs)


def on_keep_alive_notification(**kwargs):
    message = time.time()
    send_message(kwargs['reg_id'], message, 'KEEP_ALIVE', 0)


def on_register_request(**kwargs):
    name = kwargs['login']
    password = kwargs['password']
    reg_id = kwargs['reg_id']

    if not re.match('^[a-zA-Z][a-zA-Z_0-9]*$', name):
        send_message(kwargs['reg_id'], "Name should start with latin letter",
                     'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')
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
        result = con.execute("SELECT * FROM players WHERE name=?", (name, ))
        if result.rowcount > 0:
            send_message(kwargs['reg_id'], "Name already exists",
                         'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')
            return
        con.execute("INSERT INTO players (name, password, coins, online, reg_id) VALUES(?, ?, ?, ?, ?)",
                    (name, password, START_COINS, True, reg_id))
        data = '{} {} {}'.format(con.lastrowid,  name, password)
        send_message(reg_id, data, 'ENTRY_ACTIVITY', 'ENTRY_REGISTRATION_RESULT')

        cherrypy.log("Registered player with name={} and password={}".format(name, password))


def send_message(reg_ids, message, receiver, msg_type):
    if not type(reg_ids) is list:
        reg_ids = [reg_ids]
    message_data = {'message': message, 'receiver': receiver, "messageType": msg_type}
    send_data(reg_ids, message_data)


def setup_database():
    players_table_sql = "CREATE TABLE if NOT EXISTS players (id INTEGER PRIMARY KEY ASC, " \
                        "name VARCHAR(40), password VARCHAR(40), coins UNSIGNED INTEGER," \
                        "room_id INTEGER, own_number INTEGER, online INTEGER," \
                        " FOREIGN KEY(room_id) REFERENCES rooms(id))"
    rooms_table_sql = "CREATE TABLE if NOT EXISTS rooms (id INTEGER PRIMARY KEY ASC, " \
                      "name VARCHAR(40), password VARCHAR(40), game_cost INTEGER, " \
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

    cherrypy.server.socket_host = '0.0.0.0' # local computer, public available
    cherrypy.engine.subscribe('start', setup_database)
    cherrypy.quickstart(StringGeneratorWebService(), '/', conf)