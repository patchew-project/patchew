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

def build_id_checker(e):
    u = e.upper()
    def c(s):
        return u in s.get_message_id().upper()
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
    'subject': {
        'build': build_keyword_checker,
        'desc': 'Search keyword in subject'
    },
    'id': {
        'build': build_id_checker,
        'desc': 'Search by message-id'
    },
    'is': {
        'build': build_is_checker,
        'desc': '''Search by property, for example is:reviewed or is:replied.
                Multiple properties can be listed by separating with comma'''
    },
    'not': {
        'build': build_not_checker,
        'desc': '''Reverse of "is", meaning to search series that has none of the
                list properties'''
    },
    'from': {
        'build': build_from_checker,
        'desc': '''Search "From:" field, with a list of names or addresses
                separated by ",".'''
    },
    'to': {
        'build': build_to_checker,
        'desc': 'Search "To:" field'
    },
    'cc': {
        'build': build_cc_checker,
        'desc': 'Search *both* "To:" and "Cc:" field',
    },
    'age': {
        'build': build_age_checker,
        'desc': '''Search by age of series, for example age:>1w or age:1y. If
                comparison is omitted, it is compare by less than. Supported units are
                "d", "w", "m", "y".''',
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
            elif e[0] in ":+":
                t, v = "is", e[1:]
            elif e[0] in "-":
                t, v = "not", e[1:]
            elif e[0] in "<>":
                t, v = "age", e
            elif ":" in e:
                t, v = e.split(":", 2)
            else:
                t, v = 'subject', e
            if t not in _checkers:
                continue
            c = _checkers[t]['build'](v)
            if c:
                self._filters.append(c)

def build_doctext():
    r = """
Query = <TERM> <TERM> ...

Each term is <COMP>:<VALUE> or <PREFIX><VALUE> or <VALUE>, Example:

    from:Bob subject:fix cc:George age:>1w

to search all emails from Bob that have the word "fix" in subject, with George
in Cc list, and are sent before last week. And

    from:Bob subject:fix is:reviewed not:tested

to search all email from Bob that have "fix" in subject, and have been reviewed
but failed testing. It can be simplified as:

    from:Bob fix :reviewed -tested

The normal syntax, <COMP>:<VALUE> can be one of:

"""

    for k, v in _checkers.iteritems():
        r += " * %-10s - %s\n" % (k, " ".join([x.strip() for x in v['desc'].splitlines()]))
    r +="""

As in the examples, there are a few syntax shortcuts as <PREFIX><VALUE>, or
plain <VALUE>:

 * :VALUE and +VALUE equals to is:VALUE
 * -VALUE equals to not:VALUE
 * >VALUE and <VALUE equals to age:>VALUE and age:<VALUE
 * VALUE (with no prefix) equals to keyword:<value>

"""

    return r

doctext = build_doctext()
