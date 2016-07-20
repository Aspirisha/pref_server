import collections
import pycurl
import json

SERVER_KEY = "AIzaSyAhL2EX96bgmKQSgvwKCrCZjTAwsGzrHNM"
id_to_regid = {}


class MyDict(collections.MutableMapping):
    def __init__(self, maxlen, *a, **k):
        self.maxlen = maxlen
        self.d = dict(*a, **k)
        while len(self) > maxlen:
            self.popitem()

    def __iter__(self):
        return iter(self.d)

    def __len__(self):
        return len(self.d)

    def __getitem__(self, k):
        return self.d[k]

    def __delitem__(self, k):
        del self.d[k]

    def __setitem__(self, k, v):
        if k not in self and len(self) == self.maxlen:
            self.popitem()
        self.d[k] = v


class MyEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__


def send_message(reg_ids, message, receiver, msg_type):
    if not type(reg_ids) is list:
        reg_ids = [reg_ids]
    message_data = {'message': message, 'receiver': receiver, "messageType": msg_type}
    send_data(reg_ids, message_data)


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
