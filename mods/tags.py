#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from mod import PatchewModule
from mbox import parse_address
from event import register_handler, emit_event, declare_event
from api.models import Message
from api.rest import PluginMethodField

REV_BY_PREFIX = "Reviewed-by:"
BASED_ON_PREFIX = "Based-on:"

_default_config = """
[default]
tags = Tested-by, Reported-by, Acked-by, Suggested-by

"""

BUILT_IN_TAGS = [REV_BY_PREFIX, BASED_ON_PREFIX]

class SeriesTagsModule(PatchewModule):
    """

Documentation
-------------

This module is configured in "INI" style.

It has only one section named `[default]`. The only supported option is tags:

    [default]
    tags = Reviewed-by, Tested-by, Reported-by, Acked-by, Suggested-by

The `tags` option contains the tag line prefixes (must be followed by colon)
that should be treated as meaningful patch status tags, and picked up from
series cover letter, patch mail body and their replies.

"""
    name = "tags"
    default_config = _default_config

    def __init__(self):
        register_handler("MessageAdded", self.on_message_added)
        declare_event("TagsUpdate", series="message object that is updated")

        # XXX: get this list through module config?
    def get_tag_prefixes(self):
        tagsconfig = self.get_config("default", "tags", default="")
        return set([x.strip() for x in tagsconfig.split(",") if x.strip()] + BUILT_IN_TAGS)

    def update_tags(self, s):
        old = s.get_property("tags", [])
        new = self.look_for_tags(s)
        if set(old) != set(new):
            s.set_property("tags", list(set(new)))
            return True

    def on_message_added(self, event, message):
        series = message.get_series_head()
        if not series:
            return

        def newer_than(m1, m2):
            return m1.version > m2.version and m1.date >= m2.date
        for m in series.get_alternative_revisions():
            if newer_than(m, series):
                series.set_property("obsoleted-by", m.message_id)
            elif newer_than(series, m):
                m.set_property("obsoleted-by", series.message_id)

        updated = self.update_tags(series)

        for p in series.get_patches():
            updated = updated or self.update_tags(p)

        reviewers = set()
        num_reviewed = 0
        def _find_reviewers(what):
            ret = set()
            for rev_tag in [x for x in what.get_property("tags", []) if x.lower().startswith(REV_BY_PREFIX.lower())]:
                ret.add(parse_address(rev_tag[len(REV_BY_PREFIX):]))
            return ret
        for p in series.get_patches():
            first = True
            this_reviewers = _find_reviewers(p)
            if this_reviewers:
                if first:
                    num_reviewed += 1
                    first = False
                reviewers = reviewers.union(this_reviewers)
        series_reviewers = _find_reviewers(series)
        reviewers = reviewers.union(series_reviewers)
        if num_reviewed == series.get_num()[1] or series_reviewers:
            series.set_property("reviewed", True)
            series.set_property("reviewers", list(reviewers))
        if updated:
            emit_event("TagsUpdate", series=series)

    def parse_message_tags(self, m):
        r = []
        for l in m.get_body().splitlines():
            for p in self.get_tag_prefixes():
                if l.lower().startswith(p.lower()):
                    r.append(l)
        return r

    def look_for_tags(self, m):
        # Incorporate tags from non-patch replies
        r = self.parse_message_tags(m)
        for x in m.get_replies():
            if x.is_patch:
                continue
            r += self.look_for_tags(x)
        return r

    def get_tags(self, m, request, format):
        return m.get_property("tags", [])

    def rest_message_fields_hook(self, request, fields):
        fields['tags'] = PluginMethodField(obj=self)

    def prepare_message_hook(self, request, message, detailed):
        if not message.is_series_head:
            return
        if message.get_property("reviewed"):
            reviewers = message.get_property("reviewers")
            message.status_tags.append({
                "title": "Reviewed by " + ", ".join([x for x, y in reviewers]),
                "type": "success",
                "char": "R",
                })
        ob = message.get_property("obsoleted-by")
        if ob:
            new = Message.objects.find_series(ob, message.project.name)
            if new is not None:
                message.status_tags.append({
                    "title": "Has a newer version: " + new.subject,
                    "type": "default",
                    "char": "O",
                    "row_class": "obsolete"
                    })

