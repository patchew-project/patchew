#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django import template
from patchew import logviewer
from collections import deque
import io
import operator
import re

# The basic implementation uses generators.  The filters simply apply join
# to the result of the generators.

def lines_iter(value):
    if not isinstance(value, io.IOBase):
        # StringIO provides a generator to split lines.
        value = io.StringIO(value)
    # "chomp" the newlines on each line.  Using operator and map does
    # everything in the interpreter, avoiding the overhead of a generator.
    return map(operator.methodcaller('rstrip', '\r\n'), value)

# To understand grep_iter, it may help to first study this implementation
# of a "tail" iterator, which is based on the same circular array idea:
#
#    def tail_lines_iter(value, n):
#        lines = [None] * n
#        lineno = 0
#        for line in lines_iter(value):
#            lines[lineno % n] = line
#            lineno += 1
#
#        for i in range(max(lineno - n, 0), lineno):
#            yield lines[i % n]
#
# Basic "grep" prints one line when the match is on the last line, so
# "grep" is a variation on tail_lines with n=1; likewise, "grep -B1" is
# a variantion on tail_lines with n=2, etc.

def grep_iter(value, regex, n_before, n_after, sep):
    n = n_before + 1
    lines = [None] * n
    stop = lineno = 0
    for line in lines_iter(value):
        # Print the (lineno - n)-th line.  Each element of lines[] is used
        # just before it is thrown away.
        if lineno - n >= 0 and lineno - n < stop:
            yield lines[lineno % n]
        if re.search(regex, line):
            if lineno - n >= stop and sep is not None and stop > 0:
                yield sep
            stop = lineno + n_after + 1
        lines[lineno % n] = line
        lineno += 1

    for i in range(max(lineno - n, 0), min(stop, lineno)):
        yield lines[i % n]

register = template.Library()

@register.simple_tag
@register.filter
def ansi2text(value):
    return ''.join(logviewer.ansi2text(value))

@register.simple_tag
@register.filter
def tail_lines(value, n):
    lines = deque(lines_iter(value), n)
    return '\n'.join(lines)

@register.simple_tag
@register.filter
def grep(value, regex, sep=None):
    return '\n'.join(grep_iter(value, regex, 0, 0, sep))

@register.simple_tag
@register.filter
def grep_A(value, regex, n=3, sep='---'):
    return '\n'.join(grep_iter(value, regex, 0, n, sep))

@register.simple_tag
@register.filter
def grep_B(value, regex, n=3, sep='---'):
    return '\n'.join(grep_iter(value, regex, n, 0, sep))

@register.simple_tag
@register.filter
def grep_C(value, regex, n=3, sep='---'):
    return '\n'.join(grep_iter(value, regex, n, n, sep))
