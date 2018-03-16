#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.conf.urls import url
from django.http import HttpResponse, Http404
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.template import Template, Context
from django.conf import settings
from mod import PatchewModule
import smtplib
import email
import email.utils
import uuid
from api.models import Message, Project
from event import register_handler, get_events_info
from schema import *

_default_config = """
[smtp]
server = smtp.example.com
ssl = True
port = 465
username = youruser
password = yourpassword
from = your@email.com

"""

class DebugSMTP(object):
    def sendmail(*args):
        print("SMPT: debug mode, not sending\n" + "\n".join([str(x) for x in args]))

class EmailModule(PatchewModule):
    """

Documentation
-------------

Email information is configured in "INI" style:

""" + _default_config

    name = "email" # The notify method name
    default_config = _default_config

    email_schema = \
        ArraySchema("email_notification", "Email Notification",
                    desc="Email notification",
                    members=[
                        EnumSchema("event", "Event",
                                   enums=lambda: get_events_info(),
                                   required=True,
                                   desc="Which event to trigger the email notification"),
                        BooleanSchema("enabled", "Enabled",
                                      desc="Whether this event is enabled",
                                      default=True),
                        BooleanSchema("reply_to_all", "Reply to all",
                                      desc='Whether to "reply to all" if the event has an associated email message',
                                      default=False),
                        BooleanSchema("in_reply_to", "Set In-Reply-To",
                                      desc='Whether to set In-Reply-To to the message id, if the event has an associated email message',
                                      default=True),
                        BooleanSchema("set_reply_to", "Set Reply-To",
                                      desc='Whether to set Reply-To to the project mailing list, if the event has an associated email message',
                                      default=True),
                        BooleanSchema("reply_subject", "Set replying subject",
                                      desc='Whether to set Subject to "Re: xxx", if the event has an associated email message',
                                      default=True),
                        StringSchema("to", "To", desc="Send email to"),
                        StringSchema("cc", "Cc", desc="Cc list"),
                        StringSchema("subject_template", "Subject template",
                                     desc="""The django template for subject""",
                                     required=True),
                        StringSchema("body_template", "Body template",
                                     desc="The django template for email body.",
                                     multiline=True,
                                     required=True),
                    ])

    project_property_schema = \
        ArraySchema("email", desc="Configuration for email module",
                    members=[
                        MapSchema("notifications", "Email notifications",
                                   desc="Email notifications",
                                   item=email_schema),
                   ])

    def __init__(self):
        register_handler(None, self.on_event)

    def _get_smtp(self):
        server = self.get_config("smtp", "server")
        port = self.get_config("smtp", "port")
        username = self.get_config("smtp", "username")
        password = self.get_config("smtp", "password")
        ssl = self.get_config("smtp", "ssl", "getboolean")
        if settings.DEBUG:
            return DebugSMTP()
        elif ssl:
            smtp = smtplib.SMTP_SSL(server, port)
        else:
            smtp = smtplib.SMTP(server, port)
        if self.get_config("smtp", "auth", "getboolean"):
            smtp.login(username, password)
        return smtp

    def _send_series_recurse(self, sendmethod, s):
        sendmethod(s)
        for i in s.get_replies():
            self._send_series_recurse(sendmethod, i)

    def _smtp_send(self, to, cc, message):
        from_addr = self.get_config("smtp", "from")
        message["Resent-From"] = message["From"]
        for k, v in [("From", from_addr),
                     ("To", to),
                     ("Cc", cc)]:
            if not v:
                continue
            if isinstance(v, list):
                v = ", ".join(v)
            try:
                message.replace_header(k, v)
            except KeyError:
                message[k] = v
        smtp = self._get_smtp()
        recipients = []
        for x in [to, cc]:
            if not x:
                continue
            if isinstance(x, str):
                recipients += [x]
            elif isinstance(x, list):
                recipients += x
        smtp.sendmail(from_addr, recipients, message.as_string())

    def www_view_email_bounce(self, request, message_id):
        if not request.user.is_authenticated:
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

    def prepare_message_hook(self, request, message, detailed):
        if not detailed:
            return
        if message.is_series_head and request.user.is_authenticated:
            message.extra_ops.append({"url": reverse("email-bounce",
                                                     kwargs={"message_id": message.message_id}),
                                      "icon": "mail-forward",
                                      "title": "Bounce to me"})

    def _sections_by_event(self, event):
        conf = self.get_config_obj()
        for sec in conf.sections():
            if sec.startswith("mail ") and conf.get(sec, "event") == event:
                yield sec

    def _send_email(self, to, cc, headers, body):
        message = email.message.Message()
        for k, v in headers.items():
            message[k] = v
        message.set_payload(body, charset="utf-8")

        self._smtp_send(to, cc, message)

    def gen_message_id(self):
        return "<%s@patchew.org>" % uuid.uuid1()

    def get_notifications(self, project):
        ret = {}
        for k, v in project.get_properties().items():
            if not k.startswith("email.notifications."):
                continue
            tn = k[len("email.notifications."):]
            if "." not in tn:
                continue
            an = tn[tn.find(".") + 1:]
            tn = tn[:tn.find(".")]
            ret.setdefault(tn, {})
            ret[tn][an] = v
            ret[tn]["name"] = tn
        return ret

    def on_event(self, event, **params):
        class EmailCancelled(Exception):
            pass
        po = None
        mo = None
        for v in list(params.values()):
            if isinstance(v, Message):
                mo = v
                po = mo.project
                break
            elif isinstance(v, Project):
                po = v
                break
        if not po:
            return
        for nt in list(self.get_notifications(po).values()):
            headers = {}
            if not nt["enabled"]:
                continue
            if nt["event"] != event:
                continue

            def cancel_email():
                raise EmailCancelled
            params["cancel"] = cancel_email

            ctx = Context(params, autoescape=False)

            try:
                subject = Template(nt["subject_template"]).render(ctx).strip()
                body = Template(nt["body_template"]).render(ctx).strip()
                to = [x.strip() for x in Template(nt["to"]).render(ctx).strip().split()]
                cc = [x.strip() for x in Template(nt["cc"]).render(ctx).strip().split()]
            except EmailCancelled:
                continue
            if nt["reply_to_all"] and mo:
                to += [mo.get_sender_addr()]
                cc += [x[1] for x in mo.get_recipients()]
            if mo and nt["in_reply_to"]:
                headers["In-Reply-To"] = "<%s>" % mo.message_id
            if mo and nt["set_reply_to"]:
                headers["Reply-To"] = "<%s>" % mo.project.mailing_list
            if nt["reply_subject"] and mo:
                subject = "Re: " + mo.subject if not mo.subject.startswith("Re:") else mo.subject
            if not (subject and body and (to or cc)):
                continue
            headers["Subject"] = subject
            headers["Message-ID"] = email.utils.make_msgid()
            self._send_email(to, cc, headers, body)

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append({"title": "Email notifications",
                                   "class": "info",
                                   "content_html": self.build_config_html(request,
                                                                          project)})
