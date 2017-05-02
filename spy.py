# -*- coding: utf-8 -*-
"""
Created on Mon Jan 23 15:47:53 2017

@author: Zhengyi
"""
from __future__ import unicode_literals
import os
import uuid
import string
from random import sample, randint
import argparse

from pydblite.sqlite import Database, Table
import redis
from flask import Flask, session, redirect, url_for, render_template, request
from flask_session import Session
from flask_bootstrap import Bootstrap
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


from corpus import Corpus

ENABLE_REDIS = True
PROXY = True

ROOM_ID_LEN = 5
ID_RANGE = string.digits

MAX_ROOM_SIZE = 10

MAX_NUM_OF_RECORDS = {'users': 500, 'rooms': 500}
REQUEST_LIMIT = {'create': '10/minute', 'room': '2/second'}

words_500 = Corpus('corpora/words-500.txt', wsgi=False)

db = Database('WhoIsTheSpy.sqlite')

users = Table('users', db)
rooms = Table('rooms', db)

if 'users' not in db:

    users.create(('uuid', 'TEXT'), ('room', 'TEXT'),
                 ('num', 'INTEGER'))
    users.create_index('uuid')

if 'rooms' not in db:

    rooms.create(('room', 'TEXT'), ('civ_word', 'TEXT'),
                 ('spy_word', 'TEXT'), ('spy_num', 'INTEGER'),
                 ('total', 'INTEGER'), ('count', 'INTEGER'),
                 ('start', 'INTEGER'))
    rooms.create_index('room')


REDIS_URL = os.getenv('REDIS_URL', None)

app = Flask(__name__)

RATELIMIT_HEADERS_ENABLED = True

if REDIS_URL is None or ENABLE_REDIS is False:
    SESSION_TYPE = 'filesystem'
    RATELIMIT_STORAGE_URL = 'memory://'
    redis_status = False
else:
    SESSION_TYPE = 'redis'
    SESSION_REDIS = redis.from_url(REDIS_URL)
    RATELIMIT_STORAGE_URL = REDIS_URL
    redis_status = True

app.config.from_object(__name__)

Session(app)
Bootstrap(app)


def get_ip():
    if request.access_route:
        return request.access_route[-1]
    else:
        return request.remote_addr or '127.0.0.1'


key_func = get_ip if PROXY else get_remote_address

limiter = Limiter(
    app,
    key_func=key_func
)


@app.route("/")
def index():
    return render_template('index.html')


@app.route('/room/<room_id>')
@limiter.limit(REQUEST_LIMIT['room'])
def enter(room_id):
    room_record = rooms(room=room_id)
    if not room_record:
        return error('找不到该房间')

    room_record = room_record[0]
    uid = session.get('uuid', None)

    if uid is None:
        uid = uuid.uuid4().get_hex()
        session['uuid'] = uid

    user_record = users(uuid=uid)

    if not user_record or user_record[0]['room'] != room_id:
        if room_record['count'] >= room_record['total']:
            return error('房间已满')
        user_num = room_record['count'] + 1
        rooms.update(room_record, count=user_num)
        rooms.commit()
        if user_record:
            users.update(user_record[0], room=room_id,
                         num=user_num)
            users.commit()
        else:
            users.insert(uid, room_id, user_num)
            users.commit()
            db_clean(users)

        user_record = users(uuid=uid)

    user_record = user_record[0]
    user_num = user_record['num']
    if user_num == room_record['spy_num']:
        word = room_record['spy_word']
    else:
        word = room_record['civ_word']

    return render_template('room.html', room_id=room_id, room_total=room_record['total'],
                           user_num=user_num, word=word, start=room_record['start'])


@app.route('/room/')
def enter_():
    uid = session.get('uuid', None)
    if uid is not None:
        record = users(uuid=uid)
        if record:
            url = url_for('enter', room_id=record[0]['room'])
            return redirect(url)

    return error('你目前没有加入任何房间')


@app.route('/create/<int:total>')
@limiter.limit(REQUEST_LIMIT['create'])
def create(total):
    if total < 3:
        return error('需要至少3人')
    if total > MAX_ROOM_SIZE:
        return error('房间最多容纳%d人' % MAX_ROOM_SIZE)

    civ_word, spy_word = words_500.getRandom()
    while 1:
        room_id = ''.join(sample(ID_RANGE, ROOM_ID_LEN))
        if not rooms(room=room_id):
            break
    rooms.insert(room_id, civ_word, spy_word, randint(1, total),
                 total, 0, randint(1, total))
    rooms.commit()
    db_clean(rooms)

    url = url_for('enter', room_id=room_id)
    return redirect(url)


@app.route('/change/')
def change():
    uid = session.get('uuid', None)
    if uid is not None:
        record = users(uuid=uid)
        if record:
            room_id = record[0]['room']
            room_record = rooms(room=room_id)
            if not room_record:
                return error('找不到该房间')
            room_record = room_record[0]
            civ_word, spy_word = words_500.getRandom()
            total = room_record['total']
            rooms.update(room_record, civ_word=civ_word,
                         spy_word=spy_word,
                         spy_num=randint(1, total),
                         start=randint(1, total))
            rooms.commit()
            url = url_for('enter', room_id=room_id)
            return redirect(url)

    return error('你目前没有加入任何房间')


@app.route('/vote/<int:num>')
def vote(num):
    uid = session.get('uuid', None)
    if uid is not None:
        record = users(uuid=uid)
        if record:
            room_id = record[0]['room']
            room_record = rooms(room=room_id)
            if not room_record:
                return error('找不到该房间')
            is_spy = (num == room_record[0]['spy_num'])
            return render_template('vote.html', user_num=num,
                                   is_spy=is_spy)

    return error('你目前没有加入任何房间')


@app.route('/rules/')
def rules():
    return render_template('rules.html')


@app.route('/db/')
def get_db_status():
    return 'users:{}<br>rooms:{}'.format(len(users), len(rooms))


@app.route('/redis/')
def get_redis_status():
    return str(redis_status)


@app.route('/ip/')
def what_is_my_ip():
    return str(key_func())


def error(msg, status_code=400):
    return render_template('error.html', msg=msg), status_code


def db_clean(table, max_records=None, delete_ratio=0.):
    if max_records is None:
        max_records = MAX_NUM_OF_RECORDS[table.name]
    num_of_records = len(table)
    if num_of_records > max_records:
        num_of_deletes = max(int(max_records * delete_ratio),
                             num_of_records - max_records)
        for i, row in enumerate(table):
            if i >= num_of_deletes:
                break
            table.delete(row)
        table.commit()


@app.errorhandler(404)
def page_not_found(e):
    return error('找不到该页面 (Error 404)', 404)


@app.errorhandler(429)
def too_many_requests(e):
    return error('访问过于频繁（Error 429)', 429)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', nargs='?', dest='interface', default='0.0.0.0',
                        help="The interface to listen on. Default is '0.0.0.0'")
    parser.add_argument('-p', nargs='?', dest='port', type=int, default=5000,
                        help="The port of the webserver. Default is 5000")
    args = parser.parse_args()

    try:
        app.run(args.interface, args.port)
    finally:
        db.close()
