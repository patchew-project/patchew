#!/usr/bin/env python2
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Fam Zheng <fam@euphon.net>
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

import email
import email.utils
import email.header
import email.generator
import time
import datetime
import re
from util import *

def _parse_header(header):
    r = ''
    for h, c in email.header.decode_header(header):
        r += unicode(h, c) if c else h
    if '\n' in r:
        r = " ".join([x.strip() for x in r.splitlines()])
    return r

def _addr_fmt_text(name, addr):
    if name:
        return "%s <%s>" % (name, addr)
    else:
        return addr


class Message(object):
    def __init__(self, m):
        self._m = email.message_from_string(m)
        self._status = {}

    def get_subject(self, upper=False, strip_tags=False, suppress_re=None):
        """Process and return subject of the message.
           upper: convert subject to upper case.
           strip_tags: remove all the leading [xxx] tags
           suppress_re: a subject str to compare to, if ours is the same or
           only to prepend Re:, return an empty str"""
        def do_strip_tags(t):
            t = t.strip()
            while t.startswith("[") and "]" in t:
                t = t[t.find("]") + 1:].strip()
            return t
        r = _parse_header(self._m['subject'])
        if upper:
            r = r.upper()
        if strip_tags:
            r = do_strip_tags(r)

        if suppress_re:
            while len(suppress_re) < len(r) and r.upper().startswith("RE:"):
                r = r[3:].strip()
            if suppress_re == r:
                return "Re: ..."
        return r

    def get_from(self, text=False):
        name, addr = email.utils.parseaddr(_parse_header(self._m['from']))
        name = name or addr
        if text:
            return _addr_fmt_text(name, addr)
        return name, addr

    def _get_addr_list(self, field, text):
        ret = []
        f = self._m.get_all(field, [])
        addrs = email.utils.getaddresses(f)
        for name, addr in addrs:
            name = name or addr
            if text:
                ret.append(_addr_fmt_text(name, addr))
            else:
                ret.append((name, addr))
        if text:
            ret = ", ".join(ret)
        return ret

    def get_to(self, text=False):
        return self._get_addr_list("to", text)

    def get_cc(self, text=False):
        return self._get_addr_list("cc", text)

    def get_in_reply_to(self):
        return self._m['in-reply-to']

    def get_date(self, timestamp=False):
        tup = email.utils.parsedate_tz(self._m['date'])
        if tup:
            stamp = email.utils.mktime_tz(tup)
            if timestamp:
                return stamp
            return datetime.datetime.utcfromtimestamp(stamp)

    def get_message_id(self, strip_angle_brackets=False):
        r = self._m['message-id']
        if strip_angle_brackets:
            if r.startswith("<"):
                r = r[1:]
            if r.endswith(">"):
                r = r[:-1]
        return r

    def mbox(self):
        return self._m.as_string(True)

    def to_dict(self):
        r = {}
        r['date'] = self.get_date()
        r['message-id'] = self.get_message_id()
        r['in-reply-to'] = self.get_in_reply_to()
        r['subject'] = self.get_subject()
        r['untagged-subject'] = self.get_subject(strip_tags=True)
        r['from'] = self.get_from()
        r['mbox'] = self.mbox()
        return r;

    def __str__(self):
        return self.get_subject()

    def get_tags(self, upper=False):
        """Return tags extracted from the leading "[XXX] [YYY ZZZ]... in subject"""
        r = set()
        s = self.get_subject(upper=upper)
        while s.startswith('['):
            t = s[1:s.find(']')]
            for k in t.split(' '):
                r.add(k)
            if ']' in s:
                s = s[s.find(']') + 1:].strip()
        return r

    def get_version(self):
        v = 1
        for tag in self.get_tags(True):
            if tag.startswith("V"):
                try:
                    v = int(tag[1:])
                except:
                    pass
        return v

    def find_tags(self, *tags):
        """Return intersection of *tags is present in this message"""
        s = set([x.upper() for x in tags])
        return s.intersection(self.get_tags(upper=True))

    def get_body(self):
        payload = self._m.get_payload()
        body = ''
        if isinstance(payload, str):
            body = payload
        else:
            for p in payload:
                if p.get_content_type() == "text/plain":
                    body += str(p.get_payload())
        return body.decode("utf-8", "ignore")

    def get_preview(self, maxchar=1000):
        r = ""
        quote = False
        for l in self.get_body().splitlines():
            if l.startswith(">"):
                if not quote:
                    r += "..."
                    quote = True
                continue
            quote = False
            r += l
            if len(r) >= 1000:
                break
        return r

    def _find_line(self, pattern):
        rexp = re.compile(pattern)
        for l in self.get_body().splitlines():
            if rexp.match(l):
                return l

    def get_reviewed_by(self):
        """Try to find a "Reviewed-by:" line in message body"""
        prefix = "Reviewed-by:"
        r = self._find_line("^" + prefix + ".*>$")
        if r:
            return email.utils.parseaddr(r[len(prefix):].strip())
        else:
            return None

    def get_num(self):
        r = 0
        for tag in self.get_tags():
            if '/' in tag:
                n, m = tag.split('/')
                try:
                    r = int(n)
                    break
                except:
                    pass
        return r

    def get_age(self, in_sec=False):
        age = int((datetime.datetime.utcnow() - self.get_date()).total_seconds())
        if in_sec:
            return age
        return seconds_to_human(age)

    def is_reply(self):
        return self.get_subject(upper=True, strip_tags=True).startswith("RE:")

    def set_status(self, st, val):
        self._status[st] = val

    def get_status(self, st, default=None):
        return self._status.get(st, default)
