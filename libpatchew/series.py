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

class Series(Message):

    def get_patch_num(self):
        for t in self.get_tags():
            if not "/" in t:
                continue
            x, y = t.split("/", 2)
            if not x.isdigit() or not y.isdigit():
                continue
            return int(y)
        return 1

    def is_replied(self):
        return self.get_status("repliers", []) != []

    def is_reviewed(self):
        return len(self.get_status('reviewed-patches', [])) == self.get_patch_num()

def is_series(m):
    """Create and return a Series from Message if it is one, otherwise
    return None"""
    return True if m.find_tags("PULL", "PATCH", "RFC") and m.get_num() == 0 else False

