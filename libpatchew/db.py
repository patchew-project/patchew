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

from message import Message
import series
import patch
import pymongo
import datetime
import pickle
import bson.binary
import search

class MessageDuplicated(Exception):
    pass

class MessageNotFound(Exception):
    pass

def _list_add(l, *add):
    return l + [x for x in add if x not in l]

def _sensible_cmp(x, y):
    """Compare two patches by message-id sequence, otherwise date"""
    if not patch.is_patch(x) or not patch.is_patch(y):
        return -cmp(x.get_date(), y.get_date())
    a = x.get_message_id()
    b = y.get_message_id()
    while b and a.startswith(b[0]):
        a = a[1:]
        b = b[1:]
    while b and a.endswith(b[-1]):
        a = a[:-1]
        b = b[:-1]
    try:
        an = int(a)
        bn = int(b)
        return cmp(an, bn)
    except:
        return cmp(a, b)

class DB(object):
    _status_prefix = "s-"
    def __init__(self, server, port, dbname):
        self._db_name = dbname + "-default"
        self._client = pymongo.MongoClient(server, port)
        self._db = self._client[self._db_name]
        self._messages = self._db.messages
        self._identities = self._db.identities

    def reset(self):
        self._messages.remove()
        self._messages.create_index([('message-id', pymongo.DESCENDING)])
        self._messages.create_index([('in-reply-to', pymongo.DESCENDING)])
        self._messages.create_index([('date', pymongo.DESCENDING)])
        self._messages.create_index([('untagged-subject', pymongo.DESCENDING)])

    def _init_status(self, m, d):
        status = {}
        for k, v in d.iteritems():
            if k.startswith(self._status_prefix):
                m.set_status(k[len(self._status_prefix):], v)

    def _series_from_dict(self, d):
        if 'mbox' not in d:
            return None
        ret = series.Series(d['mbox'])
        self._init_status(ret, d)
        return ret

    def _message_from_dict(self, d):
        if 'mbox' not in d:
            return None
        ret = Message(d['mbox'])
        self._init_status(ret, d)
        return ret

    def get_message(self, msg_id):
        r = self._messages.find_one({"message-id": msg_id})
        if not r:
            return None
        return self._message_from_dict(r)

    def get_series(self, msg_id):
        r = self._messages.find_one({"message-id": msg_id})
        m = None
        if r:
            m = self._message_from_dict(r)
        if m and series.is_series(m):
            return self._series_from_dict(r)

    def _status_list_add(self, msg_id, field, new):
        if isinstance(new, tuple):
            new = list(new)
        l = self.get_status(msg_id, field, [])
        l = _list_add(l, new)
        self.set_status(msg_id, field, l)

    def _add_patch(self, msg_id, patch_msg_id):
        return self._status_list_add(msg_id, "patches", patch_msg_id)

    def _add_reply(self, msg_id, reply_msg_id):
        return self._status_list_add(msg_id, "replies", reply_msg_id)

    def _obsolete_previous_series(self, m):
        name = m.get_subject(strip_tags=True)
        version = m.get_version()
        prev = self._messages.find({"untagged-subject": name, "is-series": True})
        for p in prev:
            pm = self._message_from_dict(p)
            if version <= max(pm.get_status("obsoleted-by-version", 0), pm.get_version()):
                continue
            print "obsolete '%s' %d => %d" % (name, pm.get_version(), version)
            self.set_statuses(p['message-id'], {'obsoleted-by': m.get_message_id(),
                                                'obsoleted-by-version': m.get_version()})

    def _get_top_message(self, msg_id, check):
        seen = set([msg_id])
        while True:
            m = self.get_message(msg_id)
            if not m:
                return None
            if check(m):
                return m
            msg_id = m.get_in_reply_to()
            if msg_id in seen or not msg_id:
                return None
            seen.add(msg_id)

    def _get_top_series_or_patch(self, msg_id):
        return self._get_top_message(msg_id, lambda x: series.is_series(x) or patch.is_patch(x))

    def _get_top_series(self, msg_id):
        return self._get_top_message(msg_id, series.is_series)

    def process_message(self, msg_id):
        """Process a new seen msg and update db"""
        m = self.get_message(msg_id)
        assert m
        irt = m.get_in_reply_to()
        revby = m.get_reviewed_by()
        p = self._get_top_series_or_patch(msg_id)
        s = self._get_top_series(msg_id)
        if irt:
            # A reply to some other message
            self._add_reply(irt, msg_id)
            if patch.is_patch(m):
                self._add_patch(irt, msg_id)
            elif m.is_reply():
                if s:
                    self._status_list_add(s.get_message_id(), "repliers", m.get_from())
        if revby:
            if p:
                # Mark the target of review, either a patch or a series, reviewed
                self._status_list_add(p.get_message_id(), "reviewed-by", revby)
            if s:
                self._status_list_add(s.get_message_id(), "reviewers", revby)
                if patch.is_patch(p):
                    # This is a review on patch, book it in series
                    self._status_list_add(s.get_message_id(),
                                          "reviewed-patches",
                                          p.get_message_id())
                else:
                    # This is a review on series, mark all patches reviewed
                    for i in self.get_patches(s):
                        self._status_list_add(s.get_message_id(),
                                              "reviewed-patches",
                                              i.get_message_id())
        else:
            # A top message
            if series.is_series(m):
                self._obsolete_previous_series(m)

    def add_message(self, m):
        """Add a new message to DB"""
        e = self._messages.find_one({'message-id': m.get_message_id()})
        if e and e.get('from'):
            raise MessageDuplicated(e)
        d = {
            'message-id': m.get_message_id(),
            'mbox': bson.binary.Binary(m.mbox()),
            'in-reply-to': m.get_in_reply_to(),
            'date': m.get_date(),
            'from': m.get_from(),
            'subject': m.get_subject(),
            'untagged-subject': m.get_subject(strip_tags=True),
            'tags': list(m.get_tags()),
            'is-series': series.is_series(m),
        }
        if e:
            for k, v in e.iteritems():
                d[k] = d.get(k, v)
        self._messages.save(d)
        return m.get_message_id()

    def get_statuses(self, msg_id):
        r = {"message-id": msg_id}
        m = self._messages.find_one(r)
        if m:
            for k, v in m.iteritems():
                if k.startswith(self._status_prefix):
                    r[k[len(self._status_prefix):]] = v
        return r

    def get_status(self, msg_id, st, default=None):
        s = self.get_statuses(msg_id)
        return s.get(st, default)

    def set_statuses(self, msg_id, args):
        m = self._messages.find_one({"message-id": msg_id})
        if not m:
            m = {"message-id": msg_id}
        for k, v in args.iteritems():
            key = self._status_prefix + k
            if v is None and key in m:
                del m[key]
                continue
            m[key] = v
        self._messages.save(m)

    def set_status(self, msg_id, name, value):
        return self.set_statuses(msg_id, {name: value})

    def _find_series_iter(self, query="", skip=0, limit=0, sort_keys=['date']):
        q = {'is-series': True}
        sort = [(s, pymongo.DESCENDING) for s in sort_keys]

        if query:
            filter0 = search.Filter(query)
        else:
            filter0 = None
        n = 0
        for i in self._messages.find(q, sort=sort):
            s = self._series_from_dict(i)
            if s.get_status('deleted'):
                continue
            if not series.is_series(s):
                continue
            if not query or filter0.match(s):
                n += 1
                if n > skip:
                    yield s
                if limit and n > limit + skip:
                    break

    def find_series_count(self, query=""):
        num = 0
        for i in self._find_series_iter(query=query):
            num += 1
        return num

    def find_series(self, query="", skip=0, limit=0, sort_keys=['date']):
        """query all the series with tags and status with pagination, but skip
        and limit are applied before tags and status filtering"""
        for m in self._find_series_iter(query=query, skip=skip, limit=limit, sort_keys=sort_keys):
            yield m

    def delete_series(self, s):
        self.set_status(s.get_message_id(), 'deleted', True)

    def find_messages(self):
        for i in self._messages.find():
            if not i.get('mbox'):
                continue
            yield self._message_from_dict(i)

    def get_patches(self, s):
        r = [self.get_message(x) for x in s.get_status("patches", [])]
        r.sort(_sensible_cmp)
        if not r:
            r = [s]
        return r

    def get_replies(self, m):

        r = [self.get_message(x) for x in m.get_status("replies", [])]
        r.sort(_sensible_cmp)
        return r

    def save_identity_pair(self, i, key):
        self._identities.remove({'identity': i})
        self._identities.insert({'identity': i, 'key': key})

    def get_key(self, i):
        a = self._identities.find_one({'identity': i})
        if a:
            return str(a['key'])
