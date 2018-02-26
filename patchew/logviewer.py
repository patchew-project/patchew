# Convert ANSI sequences to HTML for Patchew
#
# Copyright (C) 2018 Red Hat, Inc.
#
# Author: Paolo Bonzini <pbonzini@redhat.com>

import abc
import sys

from django.views import View
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

class ANSI2HTMLConverter(object):
    def __init__(self, white_bg=False):
        self.prefix = '<pre class="ansi">'

    def _write_prefix(self):
        if self.prefix != '':
            yield self.prefix
            self.prefix = ''

    def convert(self, input):
        yield from self._write_prefix()
        yield format_html('{}', input)

    def finish(self):
        yield from self._write_prefix()
        yield '</pre>'
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
