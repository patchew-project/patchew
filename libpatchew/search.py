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

class BaseChecker(object):
    """Base class for the message filter checker types"""

    # Place holder in helper text
    placeholder = "VALUE"

    def __init__(self, prefix, expr):
        self.prefix = prefix
        self.expr = expr

class KeywordChecker(BaseChecker):
    """Search keyword in subject"""

    placeholder = "KEYWORD"
    op = ["keyword:", ""]
    def __init__(self, prefix, expr):
        self.expr = expr.upper()

    def __call__(self, m):
        return self.expr in m.get_subject(upper=True)

class MessageIDChecker(BaseChecker):
    """Exact match of message-id"""

    placeholder = "Message-id"
    op = "id:"
    def __call__(self, m):
        return m.get_message_id() == self.expr

class StateChecker(BaseChecker):
    """Check message state. Multiple states can be separated with comma, with
       OR logic. For example, "is:replied,tested,reviewed"
       Supported states:
           replied - someone has replied to this series
           reviewed - all the patches in the series is reviewed
           tested - the series passed testing
           failed - the series failed testing
           untested - the series is not tested yet
           testing - the series is under testing
           obsolete or old - the series has newer version
    """

    placeholder = "MESSAGE_ID"
    op = ["is:", ":"]
    def __init__(self, prefix, expr):
        self._subcheckers = []
        for c in [self._build_subchecker(e) for e in expr.split(",")]:
            if c:
                self._subcheckers.append(c)

    def _build_subchecker(self, p):
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
        elif p == "obsolete" or p == "old":
            return lambda s: s.get_status("obsoleted-by", None) != None

    def __call__(self, m):
        return True in [sc(m) for sc in self._subcheckers]

class ReverseChecker(BaseChecker):
    """Negative of an expression"""

    placeholder = "QUERY"
    op = ["-", "!"]
    def __init__(self, prefix, expr):
        self._subchecker = _build_checkers(expr)

    def __call__(self, m):
        return True not in [check(m) for check in self._subchecker]

class AddrChecker(BaseChecker):
    """Compare the address info of message"""

    placeholder = "ADDRESS"
    op = ["from:", "to:", "cc:"]
    def __init__(self, prefix, expr):
        self._check_from = False
        self._check_to = False
        self._check_cc = False

        if prefix == "from:":
            self._check_from = True
        elif prefix == "to:":
            self._check_to = True
        elif prefix == "from:":
            self._check_cc = True
            self._check_to = True

    def __call__(self, m):
        ret = False
        if self._check_from:
            ret = ret or self.expr in m.get_from(True)
        if self._check_to or self._check_cc:
            ret = ret or self.expr in m.get_to(True)
        if self._check_cc:
            ret = ret or self.expr in m.get_cc(True)
        return ret

class AgeChecker(BaseChecker):
    """Compare age of the message"""

    placeholder = "AGE"
    op = ["age:", ">", "<"]
    def __init__(self, prefix, expr):
        if prefix == "age:":
            if expr and expr[0] in "<>":
                self._build_exp(expr[0], expr[1:])
            else:
                self._build_exp(">", expr)
        else:
            self._build_exp(prefix, expr)

    def _build_exp(self, op, e):
        less = op == "<"
        value = ""
        unit = None
        while e and e[0].isdigit():
            value = value + e[0]
            e = e[1:]
        unit = e or "d"
        if not value:
            raise SytaxError("Cannot parse age expression %s" % e)
        value = int(value)
        sec = human_to_seconds(value, unit)
        self._sec = sec
        self._less_than = less

    def __call__(self, m):
        c = cmp(m.get_age(True), self._sec)
        return (c < 0) == self._less_than

def _build_prefix_doc():
    r = ""
    for n, t in globals().iteritems():
        if not (hasattr(t, "op") and hasattr(t, "__call__")):
            continue
        if isinstance(t.op, list):
            p = ['"%s%s"' % (o, t.placeholder) for o in t.op if o]
        else:
            p = ['"%s%s"' % (t.op, t.placeholder)]
        r += " | ".join(p) + "\n"
        r += t.__doc__ + "\n\n"
    return r

def _build_prefix_list():
    r = []
    full = set()
    for n, t in globals().iteritems():
        if hasattr(t, "op") and hasattr(t, "__call__"):
            if isinstance(t.op, list):
                for o in t.op:
                    r.append((o, t))
                    assert o not in full
                    full.add(o)
            else:
                r.append((t.op, t))
                assert t.op not in full
                full.add(t.op)
    # Longest match first
    r.sort(lambda x, y: cmp(len(x[0]), len (y[0])), reverse=True)
    return r

def _build_checkers(exp):
    r = []
    for e in exp.split(" "):
        for p, t in _prefix_list:
            if e.startswith(p):
                r.append(t(p, e[len(p):]))
    return r

class Filter(object):
    def __init__(self, exp):
        self._checkers = _build_checkers(exp)

    def match(self, s):
        for c in self._checkers:
            if not c(s):
                return False
        return True

def _build_doctext():
    r = """
Query = TERM TERM ...

Each term is <PRED><VALUE>. <PRED> is the predict verb, with the possible
options listed later. <VALUE> is the condition value to be compared against by
the predict. As a simple example:

    from:Bob subject:fix cc:George age:>1w

to search all emails from Bob that have the word "fix" in subject, with George
in Cc list, and are sent before last week.

And

    from:Bob subject:fix is:reviewed not:tested

to search all email from Bob that have "fix" in subject, and have been reviewed
but failed testing. Because there are certain alias for each predict, it can be
simplified as:

    from:Bob fix +reviewed -tested

or:

    from:Bob fix :reviewed !tested


Syntax
------

"""
    r += _build_prefix_doc()

    return r

_prefix_list = _build_prefix_list()
doctext = _build_doctext()
