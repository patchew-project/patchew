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

def seconds_to_human(sec):
    unit = 'second'
    if sec > 60:
        sec /= 60
        unit = 'minute'
        if sec > 60:
            sec /= 60
            unit = 'hour'
            if sec > 24:
                sec /= 24
                unit = 'day'
                if sec > 7:
                    sec /= 7
                    unit = 'week'
    if sec > 1:
        unit += 's'
    return sec, unit

def human_to_seconds(n, unit):
    if unit == "d":
        return n * 86400
    elif unit == "w":
        return n * 86400 * 7
    elif unit == "m":
        return n * 86400 * 30
    elif unit == "y":
        return n * 86400 * 365
    else:
        return n * 86400
