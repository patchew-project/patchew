#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.
import datetime
import email
import quopri
import re

from django.core import validators
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
import jsonfield
import lzma

from mbox import MboxMessage, decode_payload
from patchew.tags import lines_iter
from event import emit_event, declare_event
from .blobs import save_blob, load_blob
import mod


class LogEntry(models.Model):
    data_xz = models.BinaryField()

    @property
    def data(self):
        if not hasattr(self, "_data"):
            self._data = lzma.decompress(self.data_xz).decode("utf-8")
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        self.data_xz = lzma.compress(value.encode("utf-8"))


class Result(models.Model):
    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"
    VALID_STATUSES = (PENDING, SUCCESS, FAILURE, RUNNING)
    VALID_STATUSES_RE = "|".join(VALID_STATUSES)

    name = models.CharField(max_length=256)
    last_update = models.DateTimeField()
    status = models.CharField(
        max_length=7,
        validators=[
            validators.RegexValidator(
                regex=VALID_STATUSES_RE,
                message="status must be one of " + ", ".join(VALID_STATUSES),
                code="invalid",
            )
        ],
    )
    log_entry = models.OneToOneField(LogEntry, on_delete=models.CASCADE, null=True)
    data = jsonfield.JSONField(default={})

    class Meta:
        index_together = [("status", "name")]

    def is_success(self):
        return self.status == self.SUCCESS

    def is_failure(self):
        return self.status == self.FAILURE

    def is_completed(self):
        return self.is_success() or self.is_failure()

    def is_pending(self):
        return self.status == self.PENDING

    def is_running(self):
        return self.status == self.RUNNING

    def save(self, *args, **kwargs):
        self.last_update = datetime.datetime.utcnow()
        old_result = Result.objects.filter(pk=self.pk).first()
        old_status = old_result.status if old_result else None
        old_entry = old_result.log_entry if old_result else None
        super(Result, self).save(*args, **kwargs)

        if self.log_entry is None and old_entry is not None:
            # Quick way to check if the field was actually saved to the database
            new_result = Result.objects.filter(pk=self.pk).first()
            if new_result.log_entry is None:
                old_entry.delete()

        emit_event("ResultUpdate", obj=self.obj, old_status=old_status, result=self)

    @staticmethod
    def renderer_from_name(name):
        found = re.match("^[^.]*", name)
        return mod.get_module(found.group(0)) if found else None

    @property
    def renderer(self):
        return Result.renderer_from_name(self.name)

    @property
    def obj(self):
        return None

    def render(self):
        if self.renderer is None:
            return None
        return self.renderer.render_result(self)

    @property
    def log(self):
        if self.log_entry is None:
            return None
        else:
            return self.log_entry.data

    @log.setter
    def log(self, value):
        if value is None:
            self.log_entry = None
            return

        entry = self.log_entry or LogEntry()
        entry.data = value
        entry.save()
        if self.log_entry is None:
            self.log_entry = entry

    def get_log_url(self, request=None):
        if not self.is_completed() or self.renderer is None:
            return None
        log_url = self.renderer.get_result_log_url(self)
        if log_url is not None and request is not None:
            log_url = request.build_absolute_uri(log_url)
        return log_url

    def __str__(self):
        return "%s (%s)" % (self.name, self.status)


class Project(models.Model):
    name = models.CharField(
        max_length=1024, db_index=True, unique=True, help_text="The name of the project"
    )
    mailing_list = models.CharField(
        max_length=4096,
        blank=True,
        help_text=(
            "The mailing list of the project. "
            "Will be used to verify if a message belongs "
            "to this project"
        ),
    )
    prefix_tags = models.CharField(
        max_length=1024,
        blank=True,
        help_text=(
            "Whitespace separated tags that "
            "are required to be present messages' prefix. "
            "Tags led by '/' are treated with python regex match. "
            "Tags led by '!' mean these mustn't exist."
        ),
    )
    url = models.CharField(
        max_length=4096, blank=True, help_text="The URL of the project page"
    )
    git = models.CharField(
        max_length=4096,
        blank=True,
        help_text=(
            "The git repo of the project. If a "
            "branch other than 'master' is desired, add it to the "
            "end after a whitespace"
        ),
    )
    description = models.TextField(blank=True, help_text="Description of the project")
    logo = models.ImageField(blank=True, upload_to="logo", help_text="Project logo")
    display_order = models.IntegerField(
        default=0,
        help_text=("Order number of the project " "to display, higher number first"),
    )
    parent_project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text=(
            "Parent project which this "
            "project belongs to. The parent must be a "
            "top project which has "
            "parent_project=NULL"
        ),
    )
    maintainers = models.ManyToManyField(User, blank=True)
    config = jsonfield.JSONField(default={})
    properties = jsonfield.JSONField(default={})

    def __str__(self):
        return self.name

    @classmethod
    def has_project(self, project):
        return self.objects.filter(name=project).exists()

    def save(self, *args, **kwargs):
        old_project = Project.objects.filter(pk=self.pk).first()
        old_config = old_project.config if old_project else None
        super(Project, self).save(*args, **kwargs)
        if old_config != self.config:
            emit_event("SetProjectConfig", obj=self)

    def get_property(self, prop, default=None):
        x = self.properties
        *path, last = prop.split(".")
        for item in path:
            if not item in x:
                return default
            x = x[item]
        return x.get(last, default)

    def delete_property(self, prop):
        x = self.properties
        *path, last = prop.split(".")
        for item in path:
            if not item in x:
                return
            x = x[item]
        if not last in x:
            return
        old_val = x[last]
        del x[last]
        self.save()
        emit_event("SetProperty", obj=self, name=prop, value=None, old_value=old_val)

    def set_property(self, prop, value):
        if value is None:
            self.delete_property(prop)
            return
        x = self.properties
        *path, last = prop.split(".")
        for item in path:
            x = x.setdefault(item, {})
        old_val = x.get(last)
        x[last] = value
        self.save()
        emit_event("SetProperty", obj=self, name=prop, value=value, old_value=old_val)

    def total_series_count(self):
        return Message.objects.series_heads(project=self.name).count()

    def maintained_by(self, user):
        if user.is_anonymous:
            return False
        if user.is_superuser:
            return True
        if self.maintainers.filter(id=user.id).exists():
            return True
        return False

    def recognizes(self, m):
        """Test if @m is considered a message in this project"""
        addr_ok = False
        for name, addr in m.get_to() + m.get_cc():
            if addr in self.mailing_list:
                addr_ok = True
                break
        if addr_ok:
            for t in self.prefix_tags.split():
                found = False
                if t.startswith("!"):
                    t = t[1:]
                    inversed = True
                else:
                    inversed = False
                for p in m.get_prefixes():
                    if t.startswith("/"):
                        found = re.match(t[1:], p)
                    else:
                        found = t.lower() == p.lower()
                    if found:
                        if inversed:
                            return False
                        break
                if not found and not inversed:
                    return False
            return True
        return False

    def get_subprojects(self):
        return Project.objects.filter(parent_project=self)

    def get_project_head(self):
        return self.get_property("git.head")

    def set_project_head(self, new_head):
        self.set_property("git.head", new_head)

    project_head = property(get_project_head, set_project_head)

    def series_update(self, message_ids):
        updated_series = []
        for msgid in message_ids:
            if msgid.startswith("<") and msgid.endswith(">"):
                msgid = msgid[1:-1]
            mo = Message.objects.filter(
                project=self, message_id=msgid, is_merged=False
            ).first()
            if not mo:
                continue
            mo.is_merged = True
            mo.save()
            s = mo.get_series_head()
            if s:
                updated_series.append(s)
        for series in updated_series:
            for p in series.get_patches():
                if not p.is_merged:
                    break
            else:
                series.set_merged()
        return len(updated_series)

    def create_result(self, **kwargs):
        return ProjectResult(project=self, **kwargs)


class ProjectResult(Result):
    project = models.ForeignKey(Project, related_name="results",
                                on_delete=models.CASCADE)

    @property
    def obj(self):
        return self.project


declare_event(
    "SeriesComplete",
    project="project object",
    series="series instance that is marked complete",
)
declare_event(
    "SeriesMerged",
    project="project object",
    series="series instance that is marked complete",
)

declare_event("MessageAdded", message="message object that is added")


declare_event("SetProjectConfig", obj="project whose configuration was updated")


declare_event(
    "SetProperty",
    obj="object to set the property",
    name="name of the property",
    value="value of the property",
    old_value="old value if any",
)


declare_event(
    "ResultUpdate",
    obj="the updated object",
    old_status="the old result status",
    result="the new result object",
)


class MessageManager(models.Manager):
    class DuplicateMessageError(Exception):
        pass

    def project_messages(self, project):
        po = None
        if isinstance(project, Project):
            po = project
        elif isinstance(project, str):
            po = Project.objects.filter(name=project).first()
        elif isinstance(project, int):
            po = Project.objects.filter(id=project).first()
        if po is None:
            return None

        q = self.get_queryset()
        q = q.filter(project=po) | q.filter(project__parent_project=po)
        return q

    def series_heads(self, project=None):
        if project:
            q = self.project_messages(project)
            if q is None:
                return None
        else:
            q = self.get_queryset()
        return q.filter(topic__isnull=False).prefetch_related("project")

    def find_series(self, message_id, project=None):
        heads = self.series_heads(project)
        if heads is None:
            return None
        return heads.filter(message_id=message_id).first()

    def find_message(self, message_id, project):
        messages = self.project_messages(project)
        if messages is None:
            return None
        return messages.filter(message_id=message_id).first()

    def find_series_from_tag(self, tag, project):
        try:
            colon = tag.index(":")
        except ValueError:
            return None
        msgid = tag[colon + 1 :].strip()
        if msgid.startswith("<") and msgid.endswith(">"):
            msgid = msgid[1:-1]
        return self.find_series(msgid, project)

    def patches(self):
        return self.get_queryset().filter(is_patch=True)

    def update_series(self, msg):
        """Update the series' record to which @msg is replying"""
        s = msg.get_series_head()
        if not s:
            return
        if not s.last_reply_date or s.last_reply_date < msg.date:
            s.last_reply_date = msg.date
            s.save()
        if s.get_sender_addr() != msg.get_sender_addr() and (
            not s.last_comment_date or s.last_comment_date < msg.date
        ):
            s.last_comment_date = msg.date
            s.save()
        s.refresh_num_patches()
        cur, total = s.get_num()
        if cur == total and s.is_patch:
            s.set_complete()
            return
        # TODO: Handle no cover letter case
        find = set(range(1, total + 1))
        for p in s.get_patches():
            assert p.is_patch
            cur, total = p.get_num()
            if cur in find:
                find.remove(cur)
        if not find:
            s.set_complete()

    def delete_subthread(self, msg):
        for r in msg.get_replies():
            self.delete_subthread(r)
        msg.delete()

    def create(self, project, **validated_data):
        mbox = validated_data.pop("mbox")
        m = MboxMessage(mbox)
        msg = Message(**validated_data)
        if "in_reply_to" not in validated_data:
            msg.in_reply_to = m.get_in_reply_to() or ""
        msg.stripped_subject = m.get_subject(strip_tags=True)
        msg.version = m.get_version()
        msg.prefixes = m.get_prefixes()
        if m.is_series_head():
            msg.topic = Topic.objects.for_stripped_subject(msg.stripped_subject)

        msg.is_patch = m.is_patch()
        msg.patch_num = m.get_num()[0]
        msg.project = project
        msg.save_mbox(mbox)
        msg.save()
        emit_event("MessageAdded", message=msg)
        self.update_series(msg)
        return msg

    def add_message_from_mbox(self, mbox, user, project_name=None):
        def find_message_projects(m):
            return [p for p in Project.objects.all() if p.recognizes(m)]

        m = MboxMessage(mbox)
        msgid = m.get_message_id()
        if project_name:
            projects = [Project.object.get(name=project_name)]
        else:
            projects = find_message_projects(m)
        stripped_subject = m.get_subject(strip_tags=True)
        is_series_head = m.is_series_head()
        for p in projects:
            msg = Message(
                message_id=msgid,
                in_reply_to=m.get_in_reply_to() or "",
                date=m.get_date(),
                subject=m.get_subject(),
                stripped_subject=stripped_subject,
                version=m.get_version(),
                sender=m.get_from(),
                recipients=m.get_to() + m.get_cc(),
                prefixes=m.get_prefixes(),
                topic=(
                    Topic.objects.for_stripped_subject(stripped_subject)
                    if is_series_head
                    else None
                ),
                is_patch=m.is_patch(),
                patch_num=m.get_num()[0],
            )
            msg.project = p
            if self.filter(message_id=msgid, project__name=p.name).first():
                raise self.DuplicateMessageError(msgid)
            msg.save_mbox(mbox)
            msg.save()
            emit_event("MessageAdded", message=msg)
            self.update_series(msg)
        return projects


def HeaderFieldModel(**args):
    return models.CharField(max_length=4096, **args)


class QueuedSeries(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.ForeignKey("Message", on_delete=models.CASCADE)
    # Special purposed queues:
    # accept: When user marked series as "accepted"
    # reject: When user marked series as "rejected"
    # watched: When a series matches user's watched query
    name = models.CharField(max_length=1024, help_text="Name of the queue")

    class Meta:
        unique_together = ("user", "message", "name")
        index_together = [("user", "message")]


class TopicManager(models.Manager):
    def for_stripped_subject(self, stripped_subject):
        q = (
            Message.objects.filter(stripped_subject=stripped_subject)
            .order_by("date")
            .reverse()[:1]
            .values("topic")
        )
        if q:
            topic = self.get(pk=q[0]["topic"])
        else:
            topic = Topic()
            topic.save()
        return topic


class Topic(models.Model):
    objects = TopicManager()
    latest = models.ForeignKey(
        "Message", on_delete=models.SET_NULL, null=True, related_name="+"
    )

    def merge_with(self, superseded):
        if self == superseded:
            return
        Message.objects.filter(topic=self).update(topic=superseded)
        self.delete()


class Message(models.Model):
    """ Patch email message """

    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    message_id = HeaderFieldModel(db_index=True)
    in_reply_to = HeaderFieldModel(blank=True, db_index=True)
    date = models.DateTimeField(db_index=True)
    # last_reply_date and last_comment_date are subtly different.
    # last_reply_date came first and is used to sort the series by
    # reply.  It includes all messages in the thread so that newer
    # series come first, but that includes the original messages
    # making it unsuitable for implementing "has:replies".
    # last_comment_date instead is used exactly for "has:replies"
    # (it could have been a bool field "has_comment" but that would
    # be a little less flexible for future extensions).  For "has:replies"
    # we need to block messages from the original author in order to
    # not count "ping"s as replies, but that obviously makes it a
    # poor sorting order.  So here's why there are two fields.
    last_reply_date = models.DateTimeField(db_index=True, null=True)
    last_comment_date = models.DateTimeField(db_index=True, null=True)
    subject = HeaderFieldModel()
    stripped_subject = HeaderFieldModel(db_index=True)
    version = models.PositiveSmallIntegerField(default=0)
    sender = jsonfield.JSONCharField(max_length=4096, db_index=True)
    recipients = jsonfield.JSONField()
    tags = jsonfield.JSONField(default=[])
    prefixes = jsonfield.JSONField(blank=True)
    is_complete = models.BooleanField(default=False)
    is_patch = models.BooleanField()
    is_merged = models.BooleanField(default=False, blank=True)
    is_obsolete = models.BooleanField(default=False)
    is_tested = models.BooleanField(default=False)
    is_reviewed = models.BooleanField(default=False)

    # is series head if not Null
    topic = models.ForeignKey(
        "Topic", on_delete=models.CASCADE, null=True, db_index=True
    )

    # patch index number if is_patch
    patch_num = models.PositiveSmallIntegerField(null=True, blank=True)

    # number of patches we've got if series head (non-null topic)
    num_patches = models.IntegerField(null=False, default=-1, blank=True)

    queues = models.ManyToManyField(User, blank=True, through=QueuedSeries)

    objects = MessageManager()

    maintainers = jsonfield.JSONField(blank=True, default=[])
    properties = jsonfield.JSONField(default={})

    def save_mbox(self, mbox_blob):
        save_blob(mbox_blob, self.message_id)

    def get_mbox_obj(self):
        self.get_mbox()
        return self._mbox_obj

    def get_mbox(self):
        if hasattr(self, "mbox_blob"):
            return self.mbox_blob
        self.mbox_blob = load_blob(self.message_id)
        self._mbox_obj = MboxMessage(self.mbox_blob)
        return self.mbox_blob

    mbox = property(get_mbox)

    def _get_mbox_with_tags(self, series_tags=[]):
        def mbox_with_tags_iter(mbox, tags):
            regex = "^[-A-Za-z]*:"
            old_tags = set()
            lines = lines_iter(mbox)
            need_minusminusminus = False
            for line in lines:
                if line.startswith("---"):
                    need_minusminusminus = True
                    break
                yield line
                if re.match(regex, line):
                    old_tags.add(line)

            # If no --- line, tags go at the end as there's no better place
            for tag in sorted(tags):
                if (
                    tag not in old_tags
                    and not tag.startswith("Based-on")
                    and not tag.startswith("Supersedes")
                ):
                    yield tag
            if need_minusminusminus:
                yield line
            yield from lines

        mbox = self.get_mbox()
        msg = email.message_from_string(mbox)
        container = msg.get_payload(0) if msg.is_multipart() else msg
        if container.get_content_type() != "text/plain":
            return msg.as_bytes(unixfrom=True)

        payload = decode_payload(container)
        # We might be adding 8-bit trailers to a message with 7bit CTE.  For
        # patches, quoted-printable is safe and mostly human-readable.
        try:
            container.replace_header("Content-Transfer-Encoding", "quoted-printable")
        except KeyError:
            msg.add_header("Content-Transfer-Encoding", "quoted-printable")
        payload = "\n".join(
            mbox_with_tags_iter(payload, set(self.tags).union(series_tags))
        )
        payload = quopri.encodestring(payload.encode("utf-8"))
        container.set_payload(payload, charset="utf-8")
        return msg.as_bytes(unixfrom=True)

    def get_mbox_with_tags(self):
        if not self.is_patch:
            if not self.is_complete:
                return None
            messages = self.get_patches()
            series_tags = set(self.tags)
        else:
            messages = [self]
            series_tags = set()

        mbox_list = []
        for message in messages:
            mbox_list.append(message._get_mbox_with_tags(series_tags))
        return b"\n".join(mbox_list)

    def get_num(self):
        assert self.is_patch or self.is_series_head
        cur, total = 1, 1
        for tag in self.prefixes:
            if "/" in tag:
                n, m = tag.split("/")
                try:
                    cur, total = int(n), int(m)
                    break
                except Exception:
                    pass
        return cur, total

    def get_reply(self, message_id):
        r = Message.objects.get(project=self.project, message_id=message_id)
        assert r.in_reply_to == self.message_id
        return r

    def get_replies(self):
        return Message.objects.filter(
            project=self.project, in_reply_to=self.message_id
        ).order_by("patch_num")

    def get_in_reply_to_message(self):
        if not self.in_reply_to:
            return None
        return Message.objects.filter(
            project_id=self.project_id, message_id=self.in_reply_to
        ).first()

    @property
    def is_series_head(self):
        return self.topic_id is not None

    def get_series_head(self):
        s = self
        while s:
            if s.is_series_head:
                return s
            s = s.get_in_reply_to_message()
        return None

    def get_patches(self):
        if not self.is_series_head:
            raise Exception("Can not get patches for a non-series message")
        c, n = self.get_num()
        if c == n and self.is_patch:
            return [self]
        return (
            Message.objects.patches()
            .filter(project=self.project, in_reply_to=self.message_id)
            .order_by("patch_num")
        )

    def refresh_num_patches(self):
        c, n = self.get_num()
        if c == n and self.is_patch:
            self.num_patches = 1
        else:
            self.num_patches = (
                Message.objects.patches()
                .filter(project=self.project, in_reply_to=self.message_id)
                .count()
            )
        self.save()

    def get_total_patches(self):
        num = self.get_num() or (1, 1)
        return num[1] or 1

    def get_num_patches(self):
        if not self.is_series_head:
            raise Exception("Can not get patches for a non-series message")
        if self.num_patches == -1:
            self.refresh_num_patches()
        return self.num_patches

    def get_property(self, prop, default=None):
        x = self.properties
        *path, last = prop.split(".")
        for item in path:
            if not item in x:
                return default
            x = x[item]
        return x.get(last, default)

    def delete_property(self, prop):
        x = self.properties
        *path, last = prop.split(".")
        for item in path:
            if not item in x:
                return
            x = x[item]
        if not last in x:
            return
        old_val = x[last]
        del x[last]
        self.save()
        emit_event("SetProperty", obj=self, name=prop, value=None, old_value=old_val)

    def set_property(self, prop, value):
        if value is None:
            self.delete_property(prop)
            return
        x = self.properties
        *path, last = prop.split(".")
        for item in path:
            x = x.setdefault(item, {})
        old_val = x.get(last)
        x[last] = value
        self.save()
        emit_event("SetProperty", obj=self, name=prop, value=value, old_value=old_val)

    def get_sender_addr(self):
        return self.sender[1]

    def get_sender_name(self):
        return self.sender[0]

    def _get_age(self, date):
        def _seconds_to_human(sec):
            unit = "second"
            if sec > 60:
                sec /= 60
                unit = "minute"
                if sec > 60:
                    sec /= 60
                    unit = "hour"
                    if sec > 24:
                        sec /= 24
                        unit = "day"
                        if sec > 7:
                            sec /= 7
                            unit = "week"
            if sec >= 2:
                unit += "s"
            return "%s %s" % (int(sec), unit)

        age = int((datetime.datetime.utcnow() - date).total_seconds())
        if age < 0:
            return "now"
        return _seconds_to_human(age)

    def get_age(self):
        return self._get_age(self.date)

    def get_asctime(self):
        d = self.date
        wday = d.weekday() + 1
        return "%s %s %d %d:%02d:%02d %s" % (
            "MonTueWedThuFriSatSun"[wday * 3 - 3 : wday * 3],
            "JanFebMarAprMayJunJulAugSepOctNovDec"[d.month * 3 - 3 : d.month * 3],
            d.day,
            d.hour,
            d.minute,
            d.second,
            d.year,
        )

    def get_last_reply_age(self):
        return self._get_age(self.last_reply_date or self.date)

    def get_body(self):
        return self.get_mbox_obj().get_body()

    def get_preview(self, maxchar=1000):
        return self.get_mbox_obj().get_preview()

    def get_diff_stat(self):
        if not self.is_series_head:
            return None
        cur = []
        patterns = [
            r"\S*\s*\|\s*[0-9]*( \+*-*)?$",
            r"\S*\s*\|\s*Bin",
            r"\S* => \S*\s*|\s*[0-9]* \+*-*$",
            r"[0-9]* files changed",
            r"1 file changed",
            r"(create|delete) mode [0-7]+",
            r"mode change [0-7]+",
            r"rename .*\([0-9]+%\)$",
            r"copy .*\([0-9]+%\)$",
            r"rewrite .*\([0-9]+%\)$",
        ]
        ret = []
        for l in self.get_body().splitlines():
            line = l.strip()
            for p in patterns:
                if re.match(p, line):
                    cur.append(line)
                    ret = cur
                    break
            else:
                cur = []
                if ret and re.match(r"--- \S", line):
                    break
        return "\n".join(ret)

    def get_message_view_url(self):
        assert self.is_patch or self.is_series_head
        if self.is_series_head:
            return reverse(
                "series_detail",
                kwargs={"project": self.project.name, "message_id": self.message_id},
            )
        else:
            return reverse(
                "series_message",
                kwargs={
                    "project": self.project.name,
                    "thread_id": self.in_reply_to,
                    "message_id": self.message_id,
                },
            )

    def get_alternative_revisions(self):
        assert self.is_series_head
        return Message.objects.filter(project=self.project, topic=self.topic)

    def set_complete(self):
        if self.is_complete:
            return
        self.is_complete = True
        self.save()
        emit_event("SeriesComplete", project=self.project, series=self)

    def set_merged(self):
        if self.is_merged:
            return
        self.is_merged = True
        self.save()
        emit_event("SeriesMerged", project=self.project, series=self)

    def create_result(self, **kwargs):
        return MessageResult(message=self, **kwargs)

    def __str__(self):
        return self.project.name + "/" + self.subject

    class Meta:
        unique_together = ("project", "message_id")
        index_together = [
            ("topic", "project", "last_reply_date"),
            ("topic", "project", "date"),
            ("topic", "last_reply_date"),
            ("topic", "date"),
        ]


class MessageResult(Result):
    message = models.ForeignKey(Message, related_name="results",
                                on_delete=models.CASCADE)

    @property
    def obj(self):
        return self.message


class Module(models.Model):
    """ Module information """

    name = models.CharField(max_length=128, unique=True)
    config = models.TextField(blank=True)

    def __str__(self):
        return self.name


class WatchedQuery(models.Model):
    """ User watched query """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="watched_queries"
    )
    query = models.TextField(blank=False, help_text="Watched query")
