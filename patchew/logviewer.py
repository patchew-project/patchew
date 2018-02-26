# Convert ANSI sequences to HTML for Patchew
#
# Copyright (C) 2018 Red Hat, Inc.
#
# Author: Paolo Bonzini <pbonzini@redhat.com>

# Entity table based on ansi2html.c from colorized-logs.

import re
import abc
import sys

from django.views import View
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.safestring import mark_safe

class ANSI2HTMLConverter(object):
    RE_STRING = '[^\b\t\n\f\r\x1B]+'
    RE_NUMS = '[0-9]+(?:;[0-9]+)*'
    RE_CSI = r'\[\??(?:' + RE_NUMS + ')?[^;0-9]'
    RE_OSC = r'].*?(?:\x1B\\|\x07)'
    RE_CONTROL = '\x1B(?:%s|%s|[^][])|[\b\t\n\f\r]' % (RE_CSI, RE_OSC)
    RE = re.compile('(%s)|(%s)' % (RE_STRING, RE_CONTROL))

    ENTITIES = {
        '\x00' : '&#x2400;', '\x01' : '&#x2401;',  '\x02' : '&#x2402;',
        '\x03' : '&#x2403;', '\x04' : '&#x2404;',  '\x05' : '&#x2405;',
        '\x06' : '&#x2406;', '\x07' : '&#x1F514;', '\x0B' : '&#x240B;',
        '\x0E' : '&#x240E;', '\x0F' : '&#x240F;',  '\x10' : '&#x2410;',
        '\x11' : '&#x2411;', '\x12' : '&#x2412;',  '\x13' : '&#x2413;',
        '\x14' : '&#x2414;', '\x15' : '&#x2415;',  '\x16' : '&#x2416;',
        '\x17' : '&#x2417;', '\x18' : '&#x2418;',  '\x19' : '&#x2419;',
        '\x1A' : '&#x241A;', '\x1B' : '&#x241B;',  '\x1C' : '&#x241C;',
        '\x1D' : '&#x241D;', '\x1E' : '&#x241E;',  '\x1F' : '&#x241F;',
        '<'    : '&lt;',     '>'    : '&gt;',      '&'    : '&amp;',
        '\x7F' : '&#x2326;'
    }
    RE_ENTITIES = re.compile('[\x00-\x1F<>&\x7F]')

    def __init__(self, white_bg=False):
        self.prefix = '<pre class="ansi">'
        self._reset()

    def _reset(self):
        self.line = []
        self.pos = 0
        self.lazy_contents = ''
        self.lazy_accumulate = True

    # self.line holds the characters for the current line.
    # Writing can overwrite some characters if self.pos is
    # not pointing to the end of the line, and then appends.
    # Moving the cursor right can add spaces to the end.

    def _write(self, chars):
        assert not self.lazy_accumulate or self.lazy_contents == ''
        self.lazy_accumulate = False
        cur_len = len(self.line)
        if self.pos < cur_len:
            last = min(cur_len - self.pos, len(chars))
            self.line[self.pos:self.pos+last] = list(chars[0:last])
        else:
            last = 0

        if len(chars) > last:
            self.line += list(chars[last:])
        self.pos += len(chars)

    def _set_pos(self, pos):
        self.pos = pos
        if self.pos > len(self.line):
            assert not self.lazy_accumulate or self.lazy_contents == ''
            self.lazy_accumulate = False
            num = self.pos - len(self.line)
            self.line += [' '] * num

    def _write_prefix(self):
        if self.prefix != '':
            yield self.prefix
            self.prefix = ''

    def _write_span(self, text):
        yield self.RE_ENTITIES.sub(lambda x: self.ENTITIES[x.group(0)], text)

    def _write_line(self, suffix):
        # If the line consists of a single string of text with no escapes or
        # control characters, convert() special cases it and does not call
        # _write.  That simple case is handled with a single _write_span.
        if self.lazy_contents != '':
            yield from self._write_span(self.lazy_contents)
            yield suffix
            self._reset()
            return

        text = "".join(self.line)
        yield from self._write_span(text)
        yield suffix
        self._reset()

    def convert(self, input):
        yield from self._write_prefix()
        for m in self.RE.finditer(input):
            if m.group(1):
                if self.lazy_accumulate:
                    self.lazy_contents += m.group(1)
                else:
                    self._write(m.group(1))
            else:
                seq = m.group(2)
                # _write_line can deal with lazy storage.  Everything else
                # must be flushed to self.line with _write.
                if seq == '\n':
                    yield from self._write_line('\n')
                    continue
                elif seq == '\f':
                    yield from self._write_line('\n<hr>')
                    continue

                if self.lazy_contents != '':
                    content = self.lazy_contents
                    self.lazy_contents = ''
                    self._write(content)

                if seq == '\b':
                    if self.pos > 0:
                        self.pos -= 1
                elif seq == '\t':
                    self._set_pos(self.pos + (8 - self.pos % 8))
                elif seq == '\r':
                    self.pos = 0

    def finish(self):
        yield from self._write_prefix()
        yield from self._write_line('</pre>')
        self.prefix = '<pre class="ansi">'

def ansi2html(input, white_bg=False):
    c = ANSI2HTMLConverter(white_bg=white_bg)
    yield from c.convert(input)
    yield from c.finish()


class LogView(View, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def content(request, **kwargs):
        return None

    # Unfortunately <pre> items cannot be focused; for arrow keys to
    # perform scrolling in the colorbox, we need to use an <iframe>
    # and the parent window's CSS and scripts do not apply.  So this
    # prolog includes Bootstrap's pre formatting (for consistency with
    # the parent window's <pre> tags) and and a script to close the
    # colorbox on Esc.
    # Putting this in a template would be nice, but it would also
    # consume more memory because we would not be able to just
    # "yield from" into the StreamingHttpResponse.
    HTML_PROLOG = mark_safe("""<!DOCTYPE html><html><head>
<style type="text/css">*{margin:0px;padding:0px;background:#333}
pre { font-size: 13px; line-height: 1.42857143; white-space: pre-wrap; word-wrap: break-word; max-width: 100%; color: #eee}
</style>
<script type="text/javascript">
if (parent.jQuery && parent.jQuery.colorbox) {
    parent.jQuery(document).bind('keydown', function (e) {
        if (e.keyCode === 27) {
            e.preventDefault();
            parent.jQuery.colorbox.close();
        }
    });
}</script><body>""")

    def generate_html(self):
        yield self.HTML_PROLOG
        yield from ansi2html(self.text)

    def get(self, request, **kwargs):
        self.text = self.content(request, **kwargs)
        if request.GET.get('html', None) != '1':
            return HttpResponse(self.text, content_type='text/plain')

        return StreamingHttpResponse(self.generate_html())

if __name__ == "__main__":
    import io
    c = ANSI2HTMLConverter()
    # Never split lines at \r
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, newline='\n')
    for line in sys.stdin:
        for output in c.convert(line):
            sys.stdout.write(output)
    for output in c.finish():
        sys.stdout.write(output)
