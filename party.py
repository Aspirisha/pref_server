import sqlite3
from server import DB_STRING
from util import send_message, id_to_regid
import random
import math

def get_next_player(p):
    p += 1
    return p if p < 4 else 1

def get_suit(card_number):
    return (card_number - 1) // 8 + 1


class Party:
    def __init__(self, room_id):
        with sqlite3.connect(DB_STRING) as con:
            con.row_factory = sqlite3.Row
            self.room_row = con.execute('SELECT * from rooms WHERE id=?', (room_id, )).fetchone()
            self.room_id = room_id
            self.shuffler = -1

    def _reset(self):
        pass

    def init_new_distribution(self):
        self.shuffler = get_next_player(self.room_row['shuffler'])
        with sqlite3.connect(DB_STRING) as con:
            con.execute("UPDATE players SET my_current_role=-1, last_card_move=-1, current_trade_bet=-1, "
                        "cards=' ', stopped_trading=0, my_tricks=0 WHERE room_id=?", (self.room_id, ))
            con.execute("UPDATE rooms SET game_state=1, shuffler=?, whisters_number=0, current_trade_bet=0, "
                        "passers_cards_are_sent=0, current_suit=-1, current_trump=-1, cards_on_table=0 "
                        "WHERE id = ?", (self.shuffler, self.room_id, ))
            self.new_shuffle()


    def new_shuffle(self):
        cards = random.shuffle(list(range(1, 33)))
        cards = [str(cards[:10]), str(cards[11:20]), str(cards[21:30])]
        talon = str(cards[31:32])

        active = get_next_player(self.shuffler)

        with sqlite3.connect(DB_STRING) as con:
            for i in range(3):
                player = 'player{}'.format(i+1)
                con.execute("UPDATE players SET cards = ?, last_card_move = -1 WHERE id = ?",
                        (cards[i], self.room_row[player]))
                self.send_cards(cards[i], player)

            con.execute("UPDATE rooms SET talon = ?, game_state = 1, active_player = ?, "
                        "current_first_hand = ?, triplets_thrown = 0, current_trump = 0 WHERE id = ?",
                        (talon, active, active, self.room_id))

        self.send_game_state(1, active)


    def send_cards(self, cards, player):
        reg_id = id_to_regid[player]
        send_message(reg_id, cards, 'GAME_ACTIVITY', 'GAME_CARDS_ARE_SENT')


    '''
     * This function will be called each time active player is changed. It sends actual data to all
     * three players. After data is got, server and passive players wait for active player to make a move.
     * NB: first two fields of message are reserved. IT MUST BE STATE CODE and ACTIVE PLAYER number!!!
     * Existing game states:
     * 1. Trading for the talon
     * Format:
     *      state code: 1
     *      current Active player number : (1..3)
     *      current max Bet : (-1 if no bet yet)
     *      current user bets : 3 numbers separated by space, containing bets of player1, ..., player3
     *
     * 2. raspasy
     * Format:
     *      state code: 2
     *      current Active player number : (1..3)
     *      new Talon Card number : if it's first or second time, else this fiels is -1
     *
     * 3. Active player thinks what to throw away (he just got talon) and what game will he play
     * Format:
     *      state code: 3
     *      current Active player number : (1..3)
     *      min bet: bet code - for active player: his game should be not less than this
     *
     * 4. Active player has chosen his game
     * Format:
     *      state code: 4
     *      current Active player number : (1..3)
     *      player's bet: the game that in fact player is goinf to play
     * 5. Whisting player decide what to do : pass or whist (if it's not stalingrad situation)
     *
     *     state code: 5
     *     current Active player number : (1..3)
     *     roles info: 3 numbers characterizing current whist choices: -1 - hasn't decided yet, 0 - pass, 1 - whist, 2 - onside
     *
     * 6. Whisting choices are done. Both players said pass. So finish this game and start new.
     *    state code: 6
     *    current Active player number : (1..3) // no matter who is it now
     *    current scores: {(mountain1, bullet1, whists_left1, whists_right1), ..., (mountain3, bullet3, whists_left3, whists_right3)}:
     *                    it's twelve numbers separated by spaces
     *
     *  7. Whisting choices are done. One player said whist, one player said pass. Make whister to be an active player and wait for his choice
     *     about how they should play: open or close game
     *     state code: 7
     *     current Active player number : (1..3) - it's that only whister!
     *
     *  8. The only whister decided, open or close game.
     *     state code: 8
     *     current Active player number : (1..3) - it's the player that is the next after shuffler
     *     whister choice: 1 if opened, else 0
     *
     * 10. Whisting choices are done. Both players are whisting.
     *     state code: 10
     *     current Active player number : (1..3) - it's the player that is the next after shuffler
     *     roles info: 3 numbers characterizing current whist choices: -1 - hasn't decided yet, 0 - pass, 1 - whist, 2 - onside
     *
     *  9. "Real game" state.
     *     state code: 9
     *     current Active player number : (1..3)
     *     5 numbers separated by space: current suit, first player move, second player move, third player move, # of cards on table (1..3). If no move was done yet, then -1
     * 11. Playing is finished: 10 tricks are got by all players in sum
     *     state code: 11
     *     current Active player number : (1..3) - THIS NUMBER IS SENSELESS HERE
     *     current scores: {(mountain1, bullet1, whists_left1, whists_right1), ..., (mountain3, bullet3, whists_left3, whists_right3)}:
     *                    it's twelve numbers separated by spaces
     *
     *
     * ?. Normal Game is going on : active player
     *      state code:
     *      current Active player number : (1..3)
     * ?. Misere
     *      state code: 7
     *      current Active player number : (1..3)
     '''

    def send_game_state(self, game_state, active_player):
        players = {}
        with sqlite3.connect(DB_STRING) as con:
            con.row_factory = sqlite3.Row
            cur = con.execute("SELECT * FROM players WHERE room_id = ?", self.room_id);
            for row in cur:
                players[row['my_number']] = row

        message = ''
        if game_state == 1:
            message = "1 {} {} {} {} {}".format(active_player, self.room_row['current_trade_bet'],
                                           players[0]["current_trade_bet"], players[1]["current_trade_bet"],
                                           players[2]["current_trade_bet"])

        if game_state == 2:
            talon_сards = self.room_row["talon"].split(' ')
            card = -1
            if len(talon_сards) > 0:
                card = talon_сards[0]
                suit = get_suit(talon_сards[0])
                with sqlite3.connect(DB_STRING) as con:
                    con.execute("UPDATE rooms SET current_suit = ? WHERE id = ?", (suit, self.room_id))
                    if len(talon_сards) > 1:
                        con.execute("UPDATE rooms SET talon = ? WHERE id = ?", (talon_сards[1], self.room_id))
            message = "2 {} {}".format(active_player, card)

        if game_state == 3:
            message = "3 {} {} {} {} {}".format(active_player, self.room_row['talon'],
                                                players[0]['current_trade_bet'], players[1]['current_trade_bet'],
                                                players[2]['current_trade_bet'])

        if game_state == 4:
            message = "4 {} {}".format(active_player, self.room_row["current_trade_bet"])

        if game_state == 5:
            message = "5 ".format(active_player, players[0]['my_current_role'], players[1]['my_current_role'],
                                  players[2]['my_current_role'])

        if game_state == 6 or game_state == 11:
            message = "{} {} {} {} {} {} {} " \
                      "{} {} {} {} {} {} {}".format(game_state, active_player, players[0]['my_mountain'],  players[0]['my_bullet'],
                                                    players[0]['my_whists_left'], players[0]['my_whists_right'],
                                                    players[1]['my_mountain'],  players[1]['my_bullet'],
                                                    players[1]['my_whists_left'], players[1]['my_whists_right'],
                                                    players[2]['my_mountain'],  players[2]['my_bullet'],
                                                    players[2]['my_whists_left'], players[2]['my_whists_right'])

        if game_state == 7:
            message = '7 {}'.format(active_player)

        if game_state == 8:
            message = '8 {} {}'.format(active_player, self.room_row['open_game'])
            if active_player != self.room_row['trade_winner'] and self.room_row['open_game'] == 1:
                self.send_passers_and_whisters_cards()

        if game_state == 9:
            message = '9 {} {} {} {} {} {}'.format(active_player, self.room_row['current_suit'],
                                                   players[0]["last_card_move"], players[1]["last_card_move"],
                                                   players[2]["last_card_move"], self.room_row["cards_on_table"])
            if active_player != self.room_row['trade_winner'] and self.room_row['open_game'] == 1 and \
                self.room_row["passers_cards_are_sent"] == 0:
                self.send_passers_and_whisters_cards()

        if game_state == 10:
            message = '10 {} {} {} {}'.format(active_player, players[0]['my_current_role'],
                                             players[1]['my_current_role'], players[2]['my_current_role'])

        for i in range(3):
            reg_id = id_to_regid[players[i][id]]
            send_message(reg_id, message, 'GAME_ACTIVITY', 'GAME_GAME_STATE_INFO')


    def send_passers_and_whisters_cards(self):
        pass

    def process_move(self):
        pass