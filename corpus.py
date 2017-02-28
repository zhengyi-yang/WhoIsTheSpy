# -*- coding: utf-8 -*-
"""
Created on Mon Jan 23 14:53:53 2017

@author: Zhengyi
"""

import os
import codecs
from random import randint, random


class Corpus(object):

    def __init__(self, path, encoding='UTF-8', wsgi=False):
        self.path = os.path.abspath(path)
        self.encoding = encoding
        self.wsgi = wsgi
        if not wsgi:
            self.num = 0
            self.words = []
            self._load()
        else:
            self.num = None
            self.words = None

    def _load(self):
        f = codecs.open(self.path, encoding=self.encoding)
        for line in f:
            self.words.append(tuple(line.rstrip().split(u',')))
        self.num = len(self.words)
        f.close()

    def getRandom(self):
        if not self.wsgi:
            a, b = self.words[randint(0, self.num - 1)]
        else:
            f = codecs.open(self.path, encoding=self.encoding)
            count = 0
            selected = None
            for line in f:
                count += 1
                if random() * count < 1:
                    selected = line
            a, b = selected.rstrip().split(u',')

        if randint(0, 1):
            a, b = b, a
        return a, b
