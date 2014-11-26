#!/usr/bin/env python2
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Fam Zheng <famcool@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from message import Message
import series
import patch
from util import *

def build_keyword_checker(e):
    u = e.upper()
    def c(s):
        return u in s.get_subject(upper=True)
    return c

def build_is_checker(e, reverse=False):
    def build_subchecker(k):
        if p == "replied":
            return lambda s: s.is_replied()
        elif p == "reviewed":
            return lambda s: s.is_reviewed()
        elif p == 'tested':
            return lambda s: s.get_status("testing", {}).get("passed") == True
        elif p == "failed":
            return lambda s: s.get_status("testing", {}).get("passed") == False
        elif p == "untested":
            return lambda s: s.get_status("testing") == None
        elif p == "testing":
            return lambda s: s.get_status("testing", {}).get("started") == True
        elif p == "obsolete":
            return lambda s: s.get_status("obsoleted-by", None) != None

    subcheckers = []
    for p in e.split(","):
        sc = build_subchecker(p)
        if sc:
            subcheckers.append(sc)
    def c(s):
        return (True in [sc(s) for sc in subcheckers]) != reverse
    return c

def build_not_checker(e):
    return build_is_checker(e, reverse=True)

def build_addr_checker(e, addr_extract):
    search_list = e.split(",")
    def c(s):
        addr_list = addr_extract(s).upper()
        for i in search_list:
            if i.upper() in addr_list:
                return True
    return c

def build_from_checker(e):
    return build_addr_checker(e, lambda x: x.get_from(True))

def build_to_checker(e):
    return build_addr_checker(e, lambda x: x.get_to(True))

def build_cc_checker(e):
    return build_addr_checker(e, lambda x: x.get_cc(True) + "," + x.get_to(True))

def build_age_checker(e):
    less = e.startswith("<")
    value = ""
    unit = None
    while e and e[0] in "><":
        e = e[1:]
    while e and e[0].isdigit():
        value = value + e[0]
        e = e[1:]
    unit = e or "d"
    value = int(value)
    if not value:
        return lambda x: True
    sec = human_to_seconds(value, unit)
    def c(s):
        a = s.get_age(True)
        return (a < sec) == less
    return c

_checkers = {
    '': {
        'name': 'keyword',
        'build': build_keyword_checker,
        'help': 'Search keyword in subject',
    },
    'is': {
        'name': 'is',
        'build': build_is_checker,
        'help': 'Search by property, for example is:reviewed or is:replied. Multiple properties can be listed by separating with comma',
    },
    'not': {
        'name': 'not',
        'build': build_not_checker,
        'help': 'Reverse of "is", meaning to search series that has none of the list properties',
    },
    'from': {
        'name': 'from',
        'build': build_from_checker,
        'help': 'Search "From:" field, with a list of names or addresses, separated by ",".',
    },
    'to': {
        'name': 'to',
        'build': build_to_checker,
        'help': 'Similar with "from", but search "To:" field',
    },
    'cc': {
        'name': 'cc',
        'build': build_cc_checker,
        'help': 'Similar with "from", but search *both* "To:" and "Cc:" field',
    },
    'age': {
        'name': 'age',
        'build': build_age_checker,
        'help': 'Search by age of series, for example age:>1w or age:1y. If comparison is omitted, it is compare by less than. Supported units are "d", "w", "m", "y".',
    },
}

class Filter(object):
    def __init__(self, db, exp):
        self._db = db
        self._filters = []
        self.build_filters(exp)

    def match(self, s):
        for c in self._filters:
            if not c(s):
                return False
        return True

    def build_filters(self, exp):
        for e in [x.strip() for x in exp.split(" ")]:
            if not e:
                continue
            if ":" in e:
                t, v = e.split(":", 2)
            else:
                t, v = '', e
            if t not in _checkers:
                continue
            c = _checkers[t]['build'](v)
            if c:
                self._filters.append(c)
