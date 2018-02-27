# Convert ANSI sequences to HTML for Patchew
#
# Copyright (C) 2018 Red Hat, Inc.
#
# Author: Paolo Bonzini <pbonzini@redhat.com>

# Entity table and basic ESC[m parsing based on ansi2html.c from
# colorized-logs.

import re
import abc
import sys

from django.views import View
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.safestring import mark_safe

class ANSIProcessor(object):
    RE_STRING = '[^\b\t\n\f\r\x1B]+'
    RE_NUMS = '[0-9]+(?:;[0-9]+)*'
    RE_CSI = r'\[\??(?:' + RE_NUMS + ')?[^;0-9]'
    RE_OSC = r'].*?(?:\x1B\\|\x07)'
    RE_CONTROL = '\x1B(?:%s|%s|[^][])|\r\n|[\b\t\n\f\r]' % (RE_CSI, RE_OSC)
    RE = re.compile('(%s)|(%s)' % (RE_STRING, RE_CONTROL))

    def __init__(self):
        self.class_to_id = {}
        self.id_to_class = []
        self.cur_class = self._class_to_id("")
        self._reset()
        self._reset_attrs()

    def _reset_attrs(self):
        self.fg = None
        self.bg = None
        self.dim = 0
        self.bold = 0
        self.italic = 0
        self.underline = 0
        self.blink = 0
        self.inverse = 0
        self.strike = 0

    def _reset(self):
        self.line = []
        self.class_ids = []
        self.pos = 0
        self.lazy_contents = ''
        self.lazy_accumulate = True

    # self.line and self.class_ids hold the characters and style respectively
    # for the current line.  Writing can overwrite some characters if self.pos
    # is not pointing to the end of the line, and then appends.  Moving the
    # cursor right can add spaces to the end, but those are never styled.

    def _write(self, chars, class_id):
        assert not self.lazy_accumulate or self.lazy_contents == ''
        self.lazy_accumulate = False
        classes = [class_id] * len(chars)
        cur_len = len(self.line)
        if self.pos < cur_len:
            last = min(cur_len - self.pos, len(chars))
            self.line[self.pos:self.pos+last] = list(chars[0:last])
            self.class_ids[self.pos:self.pos+last] = classes[0:last]
        else:
            last = 0

        if len(chars) > last:
            self.line += list(chars[last:])
            self.class_ids += classes[last:]
        self.pos += len(chars)

    def _set_pos(self, pos):
        self.pos = pos
        if self.pos > len(self.line):
            assert not self.lazy_accumulate or self.lazy_contents == ''
            self.lazy_accumulate = False
            num = self.pos - len(self.line)
            self.line += [' '] * num
            self.class_ids += [0] * num

    @abc.abstractmethod
    def _write_span(self, text, class_id):
        pass

    # Flushing a line locates spans that have the same style, and prints those
    # with a <span> tag if they are styled.

    def _write_line(self, suffix):
        # If the line consists of a single string of text with no escapes or
        # control characters, convert() special cases it and does not call
        # _write.  That simple case is handled with a single _write_span.
        if self.lazy_contents != '':
            yield from self._write_span(self.lazy_contents, self.cur_class)
            yield suffix
            self._reset()
            return

        self.class_ids.append(-1)
        start = 0
        class_id = self.class_ids[0]
        for i in range(1, len(self.class_ids)):
            if self.class_ids[i] != class_id:
                text = "".join(self.line[start:i])
                yield from self._write_span(text, class_id)
                start = i
                class_id = self.class_ids[i]
        yield suffix
        self._reset()

    def _do_one_csi_m(self, it):
        arg = next(it)
        if arg < 10:
            if arg == 0:
                self._reset_attrs()
            elif arg == 1:
                self.bold = 1
            elif arg == 2:
                self.dim = 1
            elif arg == 3:
                self.italic = 1
            elif arg == 4:
                self.underline = 1
            elif arg == 5:
                self.blink = 1
            elif arg == 7:
                self.inverse = 1
            elif arg == 9:
                self.strike = 1
        elif arg < 30:
            if arg == 21 or arg == 22:
                self.bold = self.dim = 0
            elif arg == 23:
                self.italic = 0
            elif arg == 24:
                self.underline = 0
            elif arg == 25:
                self.blink = 0
            elif arg == 27:
                self.inverse = 0
            elif arg == 29:
                self.strike = 0
        elif (arg >= 30 and arg <= 37) or (arg >= 91 and arg <= 96):
            # we use light colors by default, so 31..36 and 91..96 are the same
            self.fg = arg % 10
        elif arg == 38:
            # 256 colors
            if next(it) == 5:
                n = next(it)
                if n < 256:
                    self.fg = ('f%d' % n, 'b%d' % n)
        elif arg == 39:
            self.fg = None
        elif (arg >= 40 and arg <= 47) or (arg >= 101 and arg <= 106):
            # we use light colors by default, so 31..36 and 91..96 are the same
            self.bg = arg % 10
        elif arg == 48:
            # 256 colors
            if next(it) == 5:
                n = next(it)
                if n < 256:
                    self.bg = ('f%d' % n, 'b%d' % n)
        elif arg == 49:
            self.bg = None
        elif arg == 90 or arg == 97:
            # the remaining light colors: dark grey and white
            self.fg = arg - 82
        elif arg == 100 or arg == 107:
            # the remaining light colors: dark grey and white
            self.bg = arg - 92

    def _write_form_feed(self):
        pass

    def _class_to_id(self, html_class):
        class_id = self.class_to_id.get(html_class, None)
        if class_id is None:
            class_id = len(self.class_to_id)
            self.class_to_id[html_class] = class_id
            self.id_to_class.append(html_class)
        return class_id

    def _compute_class(self):
        pass

    def _do_csi_m(self, it):
        try:
            while True:
                self._do_one_csi_m(it)
        except StopIteration:
            pass
        self._compute_class()

    def _do_csi_C(self, it):
        arg = next(it)
        if arg == 0:
            arg = 1
        self._set_pos(self.pos + arg)

    def _do_csi_D(self, it):
        arg = next(it)
        if arg == 0:
            arg = 1
        self._set_pos(max(0, self.pos - arg))

    def _do_csi_K(self, it):
        arg = next(it)
        if arg == 0 or arg == 2:
            assert not self.lazy_accumulate or self.lazy_contents == ''
            if self.pos < len(self.line):
                assert not self.lazy_accumulate
                del self.line[self.pos:]
                del self.class_ids[self.pos:]
                if self.pos == 0:
                    self.lazy_accumulate = True
                    return
        if arg == 1 or arg == 2:
            save_pos = self.pos
            if save_pos > 0:
                self.pos = 0
                # clearing to the beginning of the line uses unstyled spaces
                self._write(' ' * save_pos, 0)

    def _parse_csi_with_args(self, csi, func):
        if (len(csi) <= 3):
            func(iter([0]))
        else:
            # thanks to the regular expression, we know arg is a number
            # and there cannot be a ValueError
            func((int(arg) for arg in csi[2:-1].split(";")))

    def _parse_csi(self, csi):
        if csi[1] != '[':
            return

        if csi[-1] == 'J':
            save_pos = self.pos
            yield from self._write_line('')
            yield from self._write_form_feed()
            self._set_pos(save_pos)
        elif csi[-1] == 'K':
            self._parse_csi_with_args(csi, self._do_csi_K)
        elif csi[-1] == 'C':
            self._parse_csi_with_args(csi, self._do_csi_C)
        elif csi[-1] == 'D':
            self._parse_csi_with_args(csi, self._do_csi_D)
        elif csi[-1] == 'm':
            self._parse_csi_with_args(csi, self._do_csi_m)

    def convert(self, input):
        for m in self.RE.finditer(input):
            if m.group(1):
                if self.lazy_accumulate:
                    self.lazy_contents += m.group(1)
                else:
                    self._write(m.group(1), self.cur_class)
            else:
                seq = m.group(2)
                # _write_line can deal with lazy storage.  Everything else
                # must be flushed to self.line with _write.
                if seq == '\n' or seq == '\r\n':
                    yield from self._write_line('\n')
                    continue
                elif seq == '\f':
                    yield from self._write_line('\n')
                    yield from self._write_form_feed()
                    continue

                if self.lazy_contents != '':
                    content = self.lazy_contents
                    self.lazy_contents = ''
                    self._write(content, self.cur_class)

                if seq == '\b':
                    if self.pos > 0:
                        self.pos -= 1
                elif seq == '\t':
                    self._set_pos(self.pos + (8 - self.pos % 8))
                elif seq == '\r':
                    self.pos = 0
                elif len(seq) > 1:
                    yield from self._parse_csi(seq)

    def finish(self):
        yield from self._write_line('')
        self._reset_attrs()


class ANSI2TextConverter(ANSIProcessor):
    FF = '\u2500' * 72 + '\n'
    SYMBOLS = {
        '\x00' : '\u2400', '\x01' : '\u2401',      '\x02' : '\u2402',
        '\x03' : '\u2403', '\x04' : '\u2404',      '\x05' : '\u2405',
        '\x06' : '\u2406', '\x07' : '\U00001F514', '\x0B' : '\u240B',
        '\x0E' : '\u240E', '\x0F' : '\u240F',      '\x10' : '\u2410',
        '\x11' : '\u2411', '\x12' : '\u2412',      '\x13' : '\u2413',
        '\x14' : '\u2414', '\x15' : '\u2415',      '\x16' : '\u2416',
        '\x17' : '\u2417', '\x18' : '\u2418',      '\x19' : '\u2419',
        '\x1A' : '\u241A', '\x1B' : '\u241B',      '\x1C' : '\u241C',
        '\x1D' : '\u241D', '\x1E' : '\u241E',      '\x1F' : '\u241F',
        '\x7F' : '\u2326'
    }
    RE_SYMBOLS = re.compile('[\x00-\x1F\x7F]')

    def _write_span(self, text, class_id):
        yield self.RE_SYMBOLS.sub(lambda x: self.SYMBOLS[x.group(0)], text)

    def _write_form_feed(self):
        yield self.FF


class ANSI2HTMLConverter(ANSIProcessor):
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

    COLORS = [ "BLK", "RED", "GRN", "YEL", "BLU", "MAG", "CYN", "WHI",
               "HIK", "HIR", "HIG", "HIY", "HIB", "HIM", "HIC", "HIW" ]

    def __init__(self, white_bg=False):
        super(ANSI2HTMLConverter, self).__init__()
        self.default_fg = 0 if white_bg else 7
        self.default_bg = 7 if white_bg else 0
        self.prefix = '<pre class="ansi">'

    def _write_prefix(self):
        if self.prefix != '':
            yield self.prefix
            self.prefix = ''

    def _map_color(self, color, default, dim):
        # map a color assigned by _do_one_csi_m to an index in the COLORS array

        color = color if color is not None else default
        if dim:
            # must be foreground color
            if isinstance(color, int):
                # unlike vte which has a "very dark" grey, for simplicity
                # dark grey remains dark grey
                return 8 if color == default or color == 8 else color&~8
            else:
                return ('d' + color[0], 'd' + color[1])
        else:
            if isinstance(color, int):
                # use light colors by default, except for black and light grey
                # (but see bold case in _compute_class)
                return color if color == 0 or color == 7 else color|8
            else:
                return color

    def _compute_class(self):
        fg = self._map_color(self.fg, self.default_fg, self.dim)
        bg = self._map_color(self.bg, self.default_bg, False)

        # apply inverse now: "inverse dim" affects the *background* color!
        if self.inverse:
            fg, bg = bg, fg

        # bold turns foreground light grey into white
        if fg == 7 and not self.dim and self.bold:
            fg = 15

        # now compute CSS classes
        classes = []
        if isinstance(fg, int):
            if fg != self.default_fg:
                classes.append(self.COLORS[fg])
        else:
            # 256-color palette
            classes.append(fg[0])

        if isinstance(bg, int):
            if bg != self.default_bg:
                classes.append('B' + self.COLORS[bg])
        else:
            classes.append(bg[1])

        if self.bold:
            classes.append('BOLD')
        if self.italic:
            classes.append('ITA')

        if self.underline or self.strike:
            undstr = ''
            if self.underline:
                undstr += 'UND'
            if self.strike:
                undstr += 'STR'
            classes.append(undstr)

        self.cur_class = self._class_to_id(" ".join(classes))

    def _write_span(self, text, class_id):
        if class_id > 0:
            yield ('<span class="%s">' % self.id_to_class[class_id])
        yield self.RE_ENTITIES.sub(lambda x: self.ENTITIES[x.group(0)], text)
        if class_id > 0:
            yield '</span>'

    def _write_form_feed(self):
        yield '<hr>'

    def convert(self, input):
        yield from self._write_prefix()
        yield from super(ANSI2HTMLConverter, self).convert(input)

    def finish(self):
        yield from self._write_prefix()
        yield from super(ANSI2HTMLConverter, self).finish()
        yield '</pre>'
        self.prefix = '<pre class="ansi">'


def ansi2text(input):
    c = ANSI2TextConverter()
    yield from c.convert(input)
    yield from c.finish()


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
<link rel="stylesheet" href="/static/css/ansi2html.css">
<style type="text/css">*{margin:0px;padding:0px;background:#333}
pre { font-size: 13px; line-height: 1.42857143; white-space: pre-wrap; word-wrap: break-word; max-width: 100%;}
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
