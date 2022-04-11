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
from mbox import addr_db_to_rest, parse_address
from event import register_handler, emit_event, declare_event
from api.models import Message
from api.rest import PluginMethodField
import rest_framework

REV_BY_PREFIX = "Reviewed-by:"
BASED_ON_PREFIX = "Based-on:"
SUPERSEDES_PREFIX = "Supersedes:"

_default_config = """
[default]
tags = Tested-by, Reported-by, Acked-by, Suggested-by

"""

BUILT_IN_TAGS = [REV_BY_PREFIX, BASED_ON_PREFIX, SUPERSEDES_PREFIX]


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
        declare_event(
            "SeriesReviewed",
            series="message object that got Reviewed-by tags for all patches",
        )

        # XXX: get this list through module config?

    def get_tag_prefixes(self):
        tagsconfig = self.get_config("default", "tags", default="")
        return set(
            [x.strip() for x in tagsconfig.split(",") if x.strip()] + BUILT_IN_TAGS
        )

    def update_tags(self, s):
        old = s.tags
        new = self.look_for_tags(s, s)
        if set(old) != set(new):
            s.tags = list(set(new))
            s.save()
            return True

    def on_message_added(self, event, message):
        series = message.get_series_head()
        if not series:
            return

        def newer_than(m1, m2):
            if m1 == m2:
                return False
            if m1.stripped_subject == m2.stripped_subject:
                if m1.version > m2.version:
                    return m1.date >= m2.date
                if m1.version < m2.version:
                    return False
            if m2.is_obsolete and not m1.is_obsolete:
                return True
            if m1.is_obsolete and not m2.is_obsolete:
                return False
            return m1.date > m2.date

        updated = self.update_tags(series)

        for p in series.get_patches():
            updated = updated or self.update_tags(p)

        reviewers = set()
        num_reviewed = 0

        def _find_reviewers(what):
            ret = set()
            for rev_tag in [
                x for x in what.tags if x.lower().startswith(REV_BY_PREFIX.lower())
            ]:
                ret.add(parse_address(rev_tag[len(REV_BY_PREFIX) :]))
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
            need_event = not series.is_reviewed
            series.is_reviewed = True
            series.save()
            series.set_property("reviewers", list(reviewers))
            if need_event:
                emit_event("SeriesReviewed", series=series)
        if updated:
            emit_event("TagsUpdate", series=series)

        if not series.topic.latest or newer_than(series, series.topic.latest):
            series.topic.latest = series
            series.topic.save()
        for m in series.get_alternative_revisions():
            if not m.is_obsolete and m.topic.latest != m:
                m.is_obsolete = True
                m.save()

    def process_supersedes(self, series, tag):
        old = Message.objects.find_series_from_tag(tag, series.project)
        if old:
            # the newer_than test does not work when the subject changes
            assert old.topic
            series.topic = old.topic
            if old.topic.latest == old:
                old.topic.latest = series
                old.topic.save()
            old.is_obsolete = True
            old.save()
            series.topic.merge_with(old.topic)

    def parse_message_tags(self, series, m, tag_prefixes):
        r = []
        for l in m.get_body().splitlines():
            line = l.lower()
            for p in tag_prefixes:
                if line.startswith(p.lower()):
                    if line.startswith("supersedes:"):
                        self.process_supersedes(series, l)
                    r.append(l)
        return r

    def _look_for_tags(self, series, m, tag_prefixes):
        # Incorporate tags from non-patch replies
        r = self.parse_message_tags(series, m, tag_prefixes)
        for x in m.get_replies():
            if x.is_patch:
                continue
            r += self._look_for_tags(series, x, tag_prefixes)
        return r

    def look_for_tags(self, series, m):
        tag_prefixes = self.get_tag_prefixes()
        return self._look_for_tags(series, m, tag_prefixes)

    def prepare_message_hook(self, request, message, for_message_view):
        if not message.is_series_head:
            return

        if message.is_reviewed:
            reviewers = message.get_property("reviewers")
            message.status_tags.append(
                {
                    "title": "Reviewed by " + ", ".join([x for x, y in reviewers]),
                    "type": "success",
                    "char": "R",
                }
            )

        if message.is_obsolete:
            message.status_tags.append(
                {
                    "title": "Has a newer version: " + message.topic.latest.subject,
                    "type": "default",
                    "char": "O",
                    "row_class": "obsolete",
                }
            )

    def get_obsoleted_by(self, message, request, format):
        if message.is_obsolete:
            obsoleted_by = message.topic.latest.message_id
            return rest_framework.reverse.reverse(
                "series-detail",
                kwargs={"projects_pk": message.project.id, "message_id": obsoleted_by},
                request=request,
                format=format,
            )

    def get_reviewers(self, message, request, format):
        reviewers = message.get_property("reviewers", [])
        return [addr_db_to_rest(x) for x in reviewers]

    def rest_series_fields_hook(self, request, fields, detailed):
        fields["obsoleted_by"] = PluginMethodField(obj=self, required=False)
        fields["reviewers"] = PluginMethodField(obj=self, required=False)
