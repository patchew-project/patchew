import abc

from django.views import View
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

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
        return format_html('{}<pre>{}</pre>', self.HTML_PROLOG, self.text)

    def get(self, request, **kwargs):
        self.text = self.content(request, **kwargs)
        if request.GET.get('html', None) != '1':
            return HttpResponse(self.text, content_type='text/plain')

        return HttpResponse(self.generate_html())
