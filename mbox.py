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
            h = h.decode(c or 'utf-8')
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

    def get_subject(self, upper=False, strip_tags=False, suppress_re=None):
        """Process and return subject of the message.
           upper: convert subject to upper case.
           strip_tags: remove all the leading [xxx] tags
           suppress_re: a subject str to compare to, if ours is the same or
           only to prepend Re:, return an empty str"""
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

        if suppress_re:
            while len(suppress_re) < len(r) and r.upper().startswith("RE:"):
                r = r[3:].strip()
            if suppress_re == r:
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
        if msgid and msgid.startswith("<") and msgid.endswith(">"):
            msgid = msgid[1:-1]
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
        s = self.get_subject(upper=upper)
        while s.startswith('['):
            t = s[1:s.find(']')]
            for k in t.split(' '):
                r.append(k)
            if ']' in s:
                s = s[s.find(']') + 1:].strip()
        return r

    def get_version(self):
        v = 1
        for tag in self.get_prefixes(True):
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
        payload = self._m.get_payload(decode=not self._m.is_multipart())
        body = ''
        if isinstance(payload, bytes):
            body = payload.decode(self._m.get_content_charset() or 'utf-8')
        elif isinstance(payload, list):
            for p in payload:
                if p.get_content_type() == "text/plain":
                    body += p.get_payload(decode=True).\
                                decode(p.get_content_charset() or 'utf-8')
        else:
            return "<Error while getting message body: %s>" % payload
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
                n, m = tag.split('/')
                try:
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
                               "@@")

    def is_series_head(self):
        """Create and return a Series from Message if it is one, otherwise
        return None"""
        c, t = self.get_num()
        if (c, t) == (None, None) and self.is_patch():
            return True
        if c == 0:
            return True
        return False

    def get_diff_stat(self):
        state = ""
        cur = []
        patterns = [r"\S*\s*\|\s*[0-9]* \+*-*$",
                    r"[0-9]* files changed",
                    r"1 file changed",
                    r"create mode [0-7]*"
                   ]
        ret = []
        for l in self.get_body().splitlines():
            l = l.strip()
            match = False
            for p in patterns:
                if re.match(p, l):
                    match = True
                    break
            if match:
                cur.append(l)
            else:
                if cur:
                    ret = cur
                cur = []
        if cur:
            ret = cur
        return "\n".join(ret)
