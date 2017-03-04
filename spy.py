# -*- coding: utf-8 -*-
"""
Created on Mon Jan 23 15:47:53 2017

@author: Zhengyi
"""
from __future__ import unicode_literals
import uuid
import string
from random import sample, randint

from pydblite.sqlite import Database, Table
from flask import Flask, session, redirect, url_for, render_template
from flask_session import Session

from corpus import Corpus

ROOM_ID_LEN = 5
ID_RANGE = string.digits

MAX_NUM_OF_RECORDS = 1000
MAX_ROOM_SIZE = 10

words_500 = Corpus('corpora/words-500.txt', wsgi=False)

db = Database('WhoIsTheSpy.sqlite')

users = Table('users', db)
rooms = Table('rooms', db)

if not 'users' in db:

    users.create(('uuid', 'TEXT'), ('room', 'TEXT'),
                 ('num', 'INTEGER'))
    users.create_index('uuid')

if not 'rooms' in db:

    rooms.create(('room', 'TEXT'), ('civ_word', 'TEXT'),
                 ('spy_word', 'TEXT'), ('spy_num', 'INTEGER'),
                 ('total', 'INTEGER'), ('count', 'INTEGER'),
                 ('start', 'INTEGER'))
    rooms.create_index('room')


app = Flask(__name__)
SESSION_TYPE = 'filesystem'
app.config.from_object(__name__)
Session(app)


@app.route("/")
def hello():
    return render_template('index.html')


@app.route('/room/<room_id>')
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
        else:
            users.insert(uid, room_id, user_num)
            db_clean(users)
        users.commit()
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
    db_clean(rooms)
    rooms.commit()
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


def error(msg):
    return render_template('error.html', msg=msg)


def db_clean(table, delete_ratio=0.1):
    num_of_records = len(table)
    if num_of_records > MAX_NUM_OF_RECORDS:
        num_of_deletes = max(int(MAX_NUM_OF_RECORDS * delete_ratio),
                             num_of_records - MAX_NUM_OF_RECORDS)
        for i, row in enumerate(table):
            if i >= num_of_deletes:
                break
            table.delete(row)
        table.commit()

if __name__ == "__main__":

    try:
        app.run('0.0.0.0')
    finally:
        db.close()
