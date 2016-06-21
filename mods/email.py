from django.conf.urls import url
from django.http import HttpResponse, Http404
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from mod import PatchewModule
import smtplib
import email
import uuid
import traceback
from string import Template
from api.models import Message
from event import register_handler

_default_config = """
[smtp]
server = smtp.example.com
ssl = True
port = 465
username = youruser
password = yourpassword
from = your@email.com

[mail a]
enabled = false
event = TestingReport
passed = false
project = QEMU
to = your@email.com
template = template_a

"""
class EmailModule(PatchewModule):
    """

Documentation
-------------

This module is configured in "INI" style.

It has a global `[smtp]` section and one or more `[mail XXX]` sections. The
`[smtp]` section stores the usual SMTP information for sending emails:

    [smtp]
    server = smtp.example.com
    ssl = True
    port = 465
    username = youruser
    password = yourpassword
    from = your@email.com

Each `[mail XXX]` section stores a scenario for the system to send out email:

    [mail a]
    enabled = false
    event = TestingReport
    template = template_a
    to = your@email.com
    passed = false
    project = QEMU

The meaning of each option is:

  * **enabled**: Whether the email should be sent.

  * **event**: The event type of the scenario.

  * **to**: The address to which the email should be sent.

  * **template**: The email message text template.

  * Other fields are supported depending on the type of event.

"""
    name = "email" # The notify method name
    default_config = _default_config

    def __init__(self):
        register_handler("TestingReport", self.on_testing_report)

    def _get_smtp(self):
        server = self.get_config("smtp", "server")
        port = self.get_config("smtp", "port")
        username = self.get_config("smtp", "username")
        password = self.get_config("smtp", "password")
        ssl = self.get_config("smtp", "ssl", "getboolean")
        if ssl:
            smtp = smtplib.SMTP_SSL(server, port)
        else:
            smtp = smtplib.SMTP(server, port)
        smtp.login(username, password)
        return smtp

    def _send_series_recurse(self, sendmethod, s):
        sendmethod(s)
        for i in s.get_replies():
            self._send_series_recurse(sendmethod, i)

    def _smtp_send(self, to, cc, message):
        from_addr = self.get_config("smtp", "from")
        message["From"] = from_addr
        if cc:
            message["Cc"] = cc
        else:
            message.__delitem__("Cc")
        smtp = self._get_smtp()
        smtp.sendmail(from_addr, to, message.as_string())

    def www_view_email_bounce(self, request, message_id):
        if not request.user.is_authenticated():
            raise PermissionDenied()
        m = Message.objects.find_series(message_id)
        if not m:
            raise Http404("Series not found: " + message_id)
        def send_one(m):
            msg = m.get_mbox()
            message = email.message_from_string(msg)
            self._smtp_send(request.user.email, None, message)

        self._send_series_recurse(send_one, m)
        return HttpResponse("email bounced")

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^email-bounce/(?P<message_id>.*)/",
                               self.www_view_email_bounce,
                               name="email-bounce"))

    def www_series_operations_hook(self, request, series, operations):
        if request.user.is_authenticated():
            operations.append({"url": reverse("email-bounce",
                              kwargs={"message_id": series.message_id}),
                               "title": "Bounce to me"})

    def _sections_by_event(self, event):
        conf = self.get_config_obj()
        for sec in conf.sections():
            if sec.startswith("mail ") and conf.get(sec, "event") == event:
                yield sec

    def _send_email(self, to, cc, headers, template, context={}):
        t = Template(template)
        message = email.message.Message()
        for k, v in headers.iteritems():
            message[k] = v
        pld = t.safe_substitute(context)
        print pld
        message.set_payload(pld)

        self._smtp_send(to, cc, message)

    def gen_message_id(self):
        return "<%s@patchew.org>" % uuid.uuid1()

    def on_testing_report(self, event,\
                         user, tester, project, series, passed, test, log):
        conf = self.get_config_obj()
        for sec in self._sections_by_event(event):
            if not self.get_config(sec, "enabled", "getboolean", True):
                continue
            if not passed == self.get_config(sec, "passed", "getboolean"):
                continue
            if not project == project:
                continue
            try:
                ctx = {
                        "log": log,
                        "test": test,
                        "tester": tester,
                        "user": user,
                        "project": project,
                        "series": series,
                        "passed": passed}

                self._send_email(self.get_config(sec, "to"),
                                 self.get_config(sec, "cc"),
                                 {
                                     "In-Reply-To": "<%s>" % series.message_id,
                                     "Message-Id": self.gen_message_id(),
                                     "Subject": "Re: " +series.subject,
                                 },
                                 self.get_asset(self.get_config(sec, "template")),
                                 ctx)
            except Exception as e:
                traceback.print_exc(e)
