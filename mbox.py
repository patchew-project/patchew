#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import email
import email.utils
import email.header
import datetime
import re

def _parse_header(header):
    r = ''
    for h, c in email.header.decode_header(header):
        if isinstance(h, bytes):
            h = h.decode(c or 'utf-8', 'replace')
        r += h
    if '\n' in r:
        r = " ".join([x.strip() for x in r.splitlines()])
    return r

def parse_address(addr_str):
    name, addr = email.utils.parseaddr(_parse_header(addr_str))
    return name, addr

def _addr_fmt_text(name, addr):
    if name:
        return "%s <%s>" % (name, addr)
    else:
        return addr


class MboxMessage(object):
    """ Helper class to process mbox """
    def __init__(self, m):
        self._m = email.message_from_string(m)
        self._status = {}
        self._mbox = m

    def get_mbox(self):
        return self._mbox

    def get_subject(self, upper=False, strip_tags=False, suppress_re=None,
                    strip_re=False):
        """Process and return subject of the message.
           upper: convert subject to upper case.
           strip_tags: remove all the leading [xxx] tags
           suppress_re: a subject str to compare to, if ours is the same or
           only to prepend Re:, return an empty str
           strip_re: drop leading "Re:" prefixes"""
        def do_strip_tags(t):
            diff_stats = t.strip()
            while t.startswith("[") and "]" in t:
                t = t[t.find("]") + 1:].strip()
            return t
        r = _parse_header(self._m['subject'])
        if upper:
            r = r.upper()
        if strip_tags:
            r = do_strip_tags(r)

        if suppress_re or strip_re:
            while r.upper().startswith("RE:"):
                r = r[3:].strip()
            if strip_re:
                return r
            if suppress_re and suppress_re == r:
                return "Re: ..."
        return r

    def get_from(self, text=False):
        name, addr = parse_address(self._m['from'])
        name = name or addr
        if text:
            return _addr_fmt_text(name, addr)
        return name, addr

    def _get_addr_list(self, field, text):
        ret = []
        f = self._m.get_all(field, [])
        f = (_parse_header(x) for x in f)
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

    def trim_message_id(self, msgid):
        if not msgid:
            return msgid
        if msgid.startswith("<"):
            return msgid[1:msgid.find(">")]
        for x in msgid.split('\n'):
            if x.startswith("<") and x.endswith(">"):
                return x[1:-1]
        return msgid

    def get_in_reply_to(self):
        return self.trim_message_id(self._m['in-reply-to'])

    def get_date(self, timestamp=False):
        tup = email.utils.parsedate_tz(self._m['date'])
        if tup:
            stamp = email.utils.mktime_tz(tup)
            if timestamp:
                return stamp
            return datetime.datetime.utcfromtimestamp(stamp)

    def get_message_id(self):
        return self.trim_message_id(self._m['message-id'])

    def get_prefixes(self, upper=False):
        """Return tags extracted from the leading "[XXX] [YYY ZZZ]... in subject"""
        r = []
        s = self.get_subject(upper=upper, strip_re=True)
        while s.startswith('[') and ']' in s:
            t = s[1:s.find(']')]
            for k in t.split(' '):
                r.append(k)
            if ']' in s:
                s = s[s.find(']') + 1:].strip()
        return r

    def get_version(self):
        v = 1
        for tag in self.get_prefixes(True):
            if tag.startswith("PATCH"):
                tag = tag[5:]
            if tag.startswith("V"):
                try:
                    v = int(tag[1:])
                except:
                    pass
        return v

    def find_tags(self, *tags):
        """Return intersection of *tags is present in this message"""
        s = set([x.upper() for x in tags])
        return s.intersection(self.get_prefixes(upper=True))

    def get_body(self):
        def decode_payload(payload, charset):
            try:
                return payload.decode(charset or 'utf-8', errors='replace')
            except:
                if charset != 'utf-8':
                    # Still fall back from non-utf-8 to utf-8
                    return payload.decode('utf-8')
                else:
                    raise
        def _get_message_text(m):
            payload = m.get_payload(decode=not self._m.is_multipart())
            body = ''
            if m.get_content_type() == "text/plain":
                body = decode_payload(m.get_payload(decode=True),
                                      self._m.get_content_charset())
            elif isinstance(payload, list):
                for p in payload:
                    body += _get_message_text(p)
            return body
        body = _get_message_text(self._m)
        return body

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
        cur, total = None, None
        for tag in self.get_prefixes():
            if '/' in tag:
                try:
                    n, m = tag.split('/')
                    cur, total = int(n), int(m)
                    break
                except:
                    pass
        return cur, total

    def is_reply(self):
        return self.get_subject(upper=True, strip_tags=True).startswith("RE:")

    def set_status(self, st, val):
        self._status[st] = val

    def get_status(self, st, default=None):
        return self._status.get(st, default)

    def get_status_by_prefix(self, pref):
        return dict([(k, v) for k, v in self._status.items() if k.startswith(pref)])

    def _has_lines(self, text, *lines):
        i = 0
        for l in text.splitlines():
            if i == len(lines):
                break
            if l.startswith(lines[i]):
                i += 1
        return i == len(lines)

    def is_patch(self):
        """ Return true if the email body is a patch """
        body = self.get_body()
        if self.get_subject().startswith("Re:"):
            return False
        return self._has_lines(body,
                               "---",
                               "diff ",
                               "index ",
                               "---",
                               "+++",
                               "@@") or \
               self._has_lines(body,
                               "---",
                               "diff ",
                               "old mode ",
                               "new mode ")

    def is_series_head(self):
        """Create and return a Series from Message if it is one, otherwise
        return None"""
        if self.get_subject().startswith("Re:"):
            return False
        c, t = self.get_num()
        if (c, t) == (None, None) and self.is_patch():
            return True
        if c == 0:
            return True
        return False
