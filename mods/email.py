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
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.conf import settings
from mod import PatchewModule
import smtplib
import email
import email.utils
import uuid
from api.models import Message, Project
from event import register_handler, get_events_info
import schema

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
    (
        """

Documentation
-------------

Email information is configured in "INI" style:

"""
        + _default_config
    )

    name = "email"  # The notify method name
    default_config = _default_config

    email_schema = schema.ArraySchema(
        "{name}",
        "Email Notification",
        desc="Email notification",
        members=[
            schema.EnumSchema(
                "event",
                "Event",
                enums=lambda: get_events_info(),
                required=True,
                desc="Which event to trigger the email notification",
            ),
            schema.BooleanSchema(
                "enabled", "Enabled", desc="Whether this event is enabled", default=True
            ),
            schema.BooleanSchema(
                "reply_to_all",
                "Reply to all",
                desc='If set, Cc all the receipients of the email message associated to the event. Also, if set the original sender of the email message will be a recipient even if the "to" field is nonempty',
                default=False,
            ),
            schema.BooleanSchema(
                "in_reply_to",
                "Set In-Reply-To",
                desc="Whether to set In-Reply-To to the message id, if the event has an associated email message",
                default=True,
            ),
            schema.BooleanSchema(
                "set_reply_to",
                "Set Reply-To",
                desc="Whether to set Reply-To to the project mailing list, if the event has an associated email message",
                default=True,
            ),
            schema.BooleanSchema(
                "reply_subject",
                "Set replying subject",
                desc='Whether to set Subject to "Re: xxx", if the event has an associated email message',
                default=True,
            ),
            schema.BooleanSchema(
                "to_user",
                "Send to user",
                desc="Whether to set To to a user email, if the event has an associated user",
                default=False,
            ),
            schema.StringSchema("to", "To", desc="Send email to"),
            schema.StringSchema("cc", "Cc", desc="Cc list"),
            schema.StringSchema(
                "subject_template",
                "Subject template",
                desc="""The django template for subject""",
                required=True,
            ),
            schema.StringSchema(
                "body_template",
                "Body template",
                desc="The django template for email body.",
                multiline=True,
                required=True,
            ),
        ],
    )

    project_config_schema = schema.ArraySchema(
        "email",
        desc="Configuration for email module",
        members=[
            schema.MapSchema(
                "notifications",
                "Email notifications",
                desc="Email notifications",
                item=email_schema,
            )
        ],
    )

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
        for k, v in [("From", from_addr), ("To", to), ("Cc", cc)]:
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

    @method_decorator(require_POST)
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
        urlpatterns.append(
            url(
                r"^email-bounce/(?P<message_id>.*)/",
                self.www_view_email_bounce,
                name="email-bounce",
            )
        )

    def prepare_message_hook(self, request, message, for_message_view):
        if not for_message_view:
            return
        if (
            message.is_series_head
            and request.user.is_authenticated
            and request.user.email
        ):
            message.extra_ops.append(
                {
                    "url": reverse(
                        "email-bounce", kwargs={"message_id": message.message_id}
                    ),
                    "icon": "share",
                    "title": "Bounce to me",
                }
            )

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
        return self.get_project_config(project).get("notifications", {})

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
            if mo:
                if nt["reply_to_all"] or not len(to):
                    to += [mo.get_sender_addr()]
                if nt["reply_to_all"]:
                    cc += [x[1] for x in mo.recipients]
            if mo and nt["in_reply_to"]:
                headers["In-Reply-To"] = "<%s>" % mo.message_id
            if mo and nt["set_reply_to"]:
                headers["Reply-To"] = "<%s>" % mo.project.mailing_list
            if nt["reply_subject"] and mo:
                subject = (
                    "Re: " + mo.subject
                    if not mo.subject.startswith("Re:")
                    else mo.subject
                )
            if nt["to_user"] and "user" in params and params["user"].email:
                to += params["user"].email
            if not (subject and body and (to or cc)):
                continue
            headers["Subject"] = subject
            headers["Message-ID"] = email.utils.make_msgid()
            self._send_email(to, cc, headers, body)

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append(
            {
                "title": "Email notifications",
                "class": "info",
                "content_html": self.build_config_html(request, project),
            }
        )
