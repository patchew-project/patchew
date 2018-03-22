#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.


import os
import json
import datetime
import re
import uuid
import logging
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from mbox import MboxMessage
from event import emit_event, declare_event
import lzma

def save_blob(data, name=None):
    if not name:
        name = str(uuid.uuid4())
    fn = os.path.join(settings.DATA_DIR, "blob", name + ".xz")
    lzma.open(fn, 'w').write(data.encode("utf-8"))
    return name

def load_blob(name):
    fn = os.path.join(settings.DATA_DIR, "blob", name + ".xz")
    return lzma.open(fn, 'r').read().decode("utf-8")

def load_blob_json(name):
    try:
        return json.loads(load_blob(name))
    except json.decoder.JSONDecodeError as e:
        logging.error('Failed to load blob %s: %s' %(name, e))
        return None

class Project(models.Model):
    name = models.CharField(max_length=1024, db_index=True, unique=True,
                            help_text="""The name of the project""")
    mailing_list = models.CharField(max_length=4096, blank=True,
                                   help_text="""The mailing list of the project.
                                   Will be used to verify if a message belongs
                                   to this project""")
    prefix_tags = models.CharField(max_length=1024, blank=True,
                                   help_text="""Whitespace separated tags that
                                   are required to be present messages' prefix.
                                   Tags led by '/' are treated with python regex match.
                                   Tags led by "!" mean these mustn't exist.
                                   """)
    url = models.CharField(max_length=4096, blank=True,
                           help_text="""The URL of the project page""")
    git = models.CharField(max_length=4096, blank=True,
                           help_text="""The git repo of the project. If a
                           branch other than "master" is desired, add it to the
                           end after a whitespace""")
    description = models.TextField(blank=True,
                                   help_text="""Description of the project""")
    logo = models.ImageField(blank=True, upload_to="logo",
                             help_text="""Project logo""")
    display_order = models.IntegerField(default=0,
                                        help_text="""Order number of the project
                                        to display, higher number first""")
    parent_project = models.ForeignKey('Project', on_delete=models.CASCADE,
                                       blank=True, null=True,
                                       help_text="""Parent project which this
                                       project belongs to. The parent must be a
                                       top project which has
                                       parent_project=NULL""")
    maintainers = models.ManyToManyField(User, blank=True)

    def __str__(self):
        return self.name

    @classmethod
    def has_project(self, project):
        return self.objects.filter(name=project).exists()

    def get_property(self, prop, default=None):
        a = ProjectProperty.objects.filter(project=self, name=prop).first()
        if a:
            if a.blob:
                return load_blob_json(a.value)
            else:
                return json.loads(a.value)
        else:
            return default

    def get_properties(self):
        r = {}
        for m in ProjectProperty.objects.filter(project=self):
            if m.blob:
                r[m.name] = load_blob_json(m.value)
            else:
                r[m.name] = json.loads(m.value)
        return r

    def _do_set_property(self, prop, value):
        if value == None:
            ProjectProperty.objects.filter(project=self, name=prop).delete()
            return
        # TODO: drop old blob
        json_data = json.dumps(value)
        blob = len(json_data) > 1024
        if blob:
            value = save_blob(json_data)
        else:
            value = json.dumps(value)
        pp, created = ProjectProperty.objects.get_or_create(project=self,
                                                            name=prop)
        pp.value = value
        pp.blob = blob
        pp.save()

    def set_property(self, prop, value):
        old_val = self.get_property(prop)
        self._do_set_property(prop, value)
        emit_event("SetProperty", obj=self, name=prop, value=value,
                   old_value=old_val)

    def total_series_count(self):
        return Message.objects.series_heads(project=self.name).count()

    def maintained_by(self, user):
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
                    if t.startswith('/'):
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

class ProjectProperty(models.Model):
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    name = models.CharField(max_length=1024, db_index=True)
    value = models.CharField(max_length=1024)
    blob = models.BooleanField(blank=True, default=False)

    class Meta:
        unique_together = ('project', 'name',)
        verbose_name_plural = "Project Properties"

declare_event("SeriesComplete", project="project object",
              series="series instance that is marked complete")

declare_event("MessageAdded", message="message object that is added")

declare_event("SetProperty", obj="object to set the property",
              name="name of the property",
              value="value of the property",
              old_value="old value if any")

class MessageManager(models.Manager):

    class DuplicateMessageError(Exception):
        pass

    def series_heads(self, project=None):
        q = super(MessageManager, self).get_queryset()\
                .filter(is_series_head=True).prefetch_related('properties', 'project')
        if isinstance(project, str):
            po = Project.objects.get(name=project)
        elif isinstance(project, int):
            po = Project.objects.get(id=project)
        else:
            return q
        q = q.filter(project=po) | q.filter(project__parent_project=po)
        return q

    def find_series(self, message_id, project_name=None):
        return self.series_heads(project_name).filter(message_id=message_id).first()

    def patches(self):
        return super(MessageManager, self).get_queryset().\
                filter(is_patch=True)

    def update_series(self, msg):
        """Update the series' record to which @msg is replying"""
        s = msg.get_series_head()
        if not s:
            return
        if not s.last_reply_date or s.last_reply_date < msg.date:
            s.last_reply_date = msg.date
            s.save()
        if s.get_sender_addr() != msg.get_sender_addr() and \
           (not s.last_comment_date or s.last_comment_date < msg.date):
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

    def add_message_from_mbox(self, mbox, user, project_name=None):

        def find_message_projects(m):
            return [p for p in Project.objects.all() if p.recognizes(m)]

        m = MboxMessage(mbox)
        msgid = m.get_message_id()
        if project_name:
            projects = [Project.object.get(name=project_name)]
        else:
            projects = find_message_projects(m)
        for p in projects:
            msg = Message(message_id=msgid,
                          in_reply_to=m.get_in_reply_to() or "",
                          date=m.get_date(),
                          subject=m.get_subject(),
                          stripped_subject=m.get_subject(strip_tags=True),
                          version=m.get_version(),
                          sender=json.dumps(m.get_from()),
                          recipients=json.dumps(m.get_to() + m.get_cc()),
                          prefixes=json.dumps(m.get_prefixes()),
                          is_series_head=m.is_series_head(),
                          is_patch=m.is_patch(),
                          patch_num=m.get_num()[0])
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

class Message(models.Model):
    """ Patch email message """

    project = models.ForeignKey('Project', on_delete=models.CASCADE)
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
    sender = HeaderFieldModel(db_index=True)
    recipients = models.TextField()
    # JSON encoded list
    prefixes = models.TextField(blank=True)
    is_series_head = models.BooleanField()
    is_complete = models.BooleanField(default=False)
    is_patch = models.BooleanField()
    is_merged = models.BooleanField(default=False, blank=True)
    # patch index number if is_patch
    patch_num = models.PositiveSmallIntegerField(null=True, blank=True)

    # number of patches we've got if is_series_head
    num_patches = models.IntegerField(null=False, default=-1, blank=True)

    objects = MessageManager()

    def save_mbox(self, mbox):
        save_blob(mbox, self.message_id)

    def get_mbox_obj(self):
        self.get_mbox()
        return self._mbox_obj

    def get_mbox(self):
        if hasattr(self, "mbox"):
            return self.mbox
        self.mbox = load_blob(self.message_id)
        self._mbox_obj = MboxMessage(self.mbox)
        return self.mbox

    def get_prefixes(self):
        return json.loads(self.prefixes)

    def get_num(self):
        assert self.is_patch or self.is_series_head
        cur, total = 1, 1
        for tag in self.get_prefixes():
            if '/' in tag:
                n, m = tag.split('/')
                try:
                    cur, total = int(n), int(m)
                    break
                except:
                    pass
        return cur, total

    def get_reply(self, message_id):
        r = Message.objects.get(project=self.project, message_id=message_id)
        assert r.in_reply_to == self.message_id
        return r

    def get_replies(self):
        return Message.objects.filter(project=self.project,
                                      in_reply_to=self.message_id).\
                                      order_by('patch_num')

    def get_in_reply_to_message(self):
        if not self.in_reply_to:
            return None
        return Message.objects.filter(project_id=self.project_id,
                                      message_id=self.in_reply_to).first()

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
        return Message.objects.patches().filter(project=self.project,
                                                in_reply_to=self.message_id)\
                             .order_by('patch_num')

    def refresh_num_patches(self):
        c, n = self.get_num()
        if c == n and self.is_patch:
            self.num_patches = 1
        else:
            self.num_patches = \
                Message.objects.patches().filter(project=self.project,
                                                 in_reply_to=self.message_id)\
                                .count()
        self.save()

    def get_total_patches(self):
        num = self.get_num() or (1,1)
        return num[1] or 1

    def get_num_patches(self):
        if not self.is_series_head:
            raise Exception("Can not get patches for a non-series message")
        if self.num_patches == -1:
            self.refresh_num_patches()
        return self.num_patches

    def get_property(self, prop, default=None):
        return self.get_properties().get(prop, default)

    def get_properties(self):
        if hasattr(self, '_properties'):
            if self._properties is not None:
                return self._properties
            else:
                # The prefetch cache is invalidated, query again
                all_props = MessageProperty.objects.filter(message=self)
        else:
            all_props = self.properties.all()
        r = {}
        for m in all_props:
            if m.blob:
                r[m.name] = load_blob_json(m.value)
            else:
                r[m.name] = json.loads(m.value)
        self._properties = r
        return r

    def _do_set_property(self, prop, value):
        if value == None:
            MessageProperty.objects.filter(message=self, name=prop).delete()
            return
        json_data = json.dumps(value)
        blob = len(json_data) > 1024
        mp, created = MessageProperty.objects.get_or_create(message=self,
                                                            name=prop)
        # TODO: drop old blob
        if blob:
            value = save_blob(json_data)
        else:
            value = json_data
        mp.value = value
        mp.blob = blob
        mp.save()
        # Invalidate cache
        self._properties = None

    def set_property(self, prop, value):
        old_val = self.get_property(prop)
        self._do_set_property(prop, value)
        emit_event("SetProperty", obj=self, name=prop, value=value,
                   old_value=old_val)

    def get_sender(self):
        return json.loads(self.sender)

    def get_recipients(self):
        return json.loads(self.recipients)

    def get_sender_addr(self):
        return self.get_sender()[1]

    def get_sender_name(self):
        return self.get_sender()[0]

    def _get_age(self, date):
        def _seconds_to_human(sec):
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
            if sec >= 2:
                unit += 's'
            return "%s %s" % (int(sec), unit)

        age = int((datetime.datetime.utcnow() - date).total_seconds())
        if age < 0:
            return "now"
        return _seconds_to_human(age)

    def get_age(self):
        return self._get_age(self.date)

    def get_asctime(self):
        d = self.date
        wday = d.weekday()+1;
        return '%s %s %d %d:%02d:%02d %s' % (
                "MonTueWedThuFriSatSun"[wday*3-3:wday*3],
                "JanFebMarAprMayJunJulAugSepOctNovDec"[d.month*3-3:d.month*3],
                d.day, d.hour, d.minute, d.second, d.year)

    def get_last_reply_age(self):
        return self._get_age(self.last_reply_date)

    def get_body(self):
        return self.get_mbox_obj().get_body()

    def get_preview(self, maxchar=1000):
        return self.get_mbox_obj().get_preview()

    def get_diff_stat(self):
        body = self.get_body()
        if not self.is_series_head:
            return None
        state = ""
        cur = []
        patterns = [r"\S*\s*\|\s*[0-9]*( \+*-*)?$",
                    r"\S* => \S*\s*|\s*[0-9]* \+*-*$",
                    r"[0-9]* files changed",
                    r"1 file changed",
                    r"(create|delete) mode [0-7]+",
                    r"mode change [0-7]+",
                    r"rename ",
                   ]
        ret = []
        for l in self.get_body().splitlines():
            l = l.strip()
            match = False
            for p in patterns:
                if re.match(p, l):
                    match = True
                    break
            if match:
                cur.append(l)
            else:
                if cur:
                    ret = cur
                cur = []
        if cur:
            ret = cur
        return "\n".join(ret)

    def get_message_view_url(self):
        assert self.is_patch or self.is_series_head
        if self.is_series_head:
            return reverse("series_detail",
                           kwargs={
                               'project': self.project.name,
                               'message_id': self.message_id
                           })
        else:
            return reverse("series_message",
                           kwargs={
                               'project': self.project.name,
                               'thread_id': self.in_reply_to,
                               'message_id': self.message_id
                           })

    def get_alternative_revisions(self):
        assert self.is_series_head
        return Message.objects.series_heads().filter(project=self.project,
                                                     stripped_subject=self.stripped_subject)

    def set_complete(self):
        if self.is_complete:
            return
        self.is_complete = True
        self.save()
        emit_event("SeriesComplete", project=self.project, series=self)

    def __str__(self):
        return self.subject

    class Meta:
        unique_together = ('project', 'message_id',)

class MessageProperty(models.Model):
    message = models.ForeignKey('Message', on_delete=models.CASCADE,
                                related_name='properties')
    name = models.CharField(max_length=256)
    # JSON encoded value
    value = models.CharField(max_length=1024)
    blob = models.BooleanField(blank=True, default=False)

    def __str__(self):
        if len(self.value) > 30:
            val_prev = self.value[:30] + "..."
        else:
            val_prev = self.value
        return "%s: %s = %s" % (self.message.subject, self.name, val_prev)

    class Meta:
        unique_together = ('message', 'name',)
        verbose_name_plural = "Message Properties"

class Module(models.Model):
    """ Module information """
    name = models.CharField(max_length=128, unique=True)
    enabled = models.BooleanField(default=True)
    config = models.TextField(blank=True)

    def __str__(self):
        return self.name
