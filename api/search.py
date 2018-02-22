#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from .models import Message
from django.db.models import Q

class InvalidSearchTerm(Exception):
    pass

class SearchEngine(object):
    """

The general form of search string is a list of terms separated with space:

    QUERY = TERM TERM ...

Each term can be either a plain keyword, or a predict in the form of
`PRED:EXP`, where PRED is the predefined filter and EXP is the parameters to be
applied to the filter. As a simple example:

    bugfix from:Bob to:George age:>1w

to search emails titled as 'bugfix' (a subject keyword filter) from Bob (a
sender filter) to George (a recipient filter) before 1 week ago (an age
filter).

or

    bugfix from:Bob is:reviewed not:obsoleted

to search all emails from Bob that have "bugfix" in subject, and have been
reviewed but is not obsoleted (by a new revision of this series). Because there
are syntax shortcut for some predicts, it can be simplified as:

    from:Bob fix +reviewed -tested

---

## Supported filter types

### Search by age

 - Syntax: age:AGE
 - Syntax: >AGE
 - Syntax: <AGE

Filter by age of the message. Supports "d" (day), "w" (week), "m" (month) and "y" (year) as units. Examples:

 - age:1d
 - age:>2d
 - age:<1w
 - <1m
 - \>1w

---

### Search by series state

Syntax:

 - is:reviewed - all the patches in the series is reviewed
 - is:obsolete or is:old - the series has newer version
 - is:complete - the series has all the patches it contains
 - is:merged - the series is included in the project's git tree
 - is:pull - the series is a pull request
 - has:replies - the series received a reply (apart from patches sent by the submitter)

Example:

    is:reviewed

---

### Search addresses

 - Syntax: from:ADDRESS
 - Syntax: to:ADDRESS

Compare the address info of message. Example:

    from:alice to:bob

---

### Reverse condition

 - Syntax: !TERM

Negative of an expression. Example:

    !is:reviewed     (query series that are not reviewed)
    !has:replies     (query series that have not received any comment)

---

### Search by message id

 - Syntax: id:MESSAGE-ID

Exact match of message-id. Example:

    id:<1416902879-17422-1-git-send-email-user@domain.com>

or

    id:1416902879-17422-1-git-send-email-user@domain.com

---

### Search by text

 - Syntax: KEYWORD

Search text keyword in the email message. Example:

    regression

"""
    def _process_term(self, query, term, neg=False):
        """ Return a Q object that will be applied to the query """
        def as_keywords(t):
            self._last_keywords.append(t)
            return Q(subject__icontains=t)

        if term.startswith("!"):
            return self._process_term(query, term[1:], not neg)
        if term.startswith("age:"):
            cond = term[term.find(":") + 1:]
            q = self._process_age_term(query, cond)
        elif term[0] in "<>":
            q = self._process_age_term(query, term)
        elif term.startswith("from:"):
            cond = term[term.find(":") + 1:]
            q = Q(sender__icontains=cond)
        elif term.startswith("to:"):
            cond = term[term.find(":") + 1:]
            q = Q(recipients__icontains=cond)
        elif term.startswith("subject:"):
            cond = term[term.find(":") + 1:]
            q = Q(subject__icontains=cond)
        elif term.startswith("id:"):
            cond = term[term.find(":") + 1:]
            if cond[0] == "<" and cond[-1] == ">":
                cond = cond[1:-1]
            q = Q(message_id=cond)
        elif term.startswith("is:") or term.startswith("not:") or term[0] in "+-":
            if term[0] in "+-":
                cond = term[1:]
                lneg = term[0] == "-"
            else:
                cond = term[term.find(":") + 1:]
                lneg = term.startswith("not:")
            if cond == "complete":
                q = Q(is_complete=True)
            elif cond == "pull":
                q = Q(subject__contains='[PULL') | Q(subject__contains='[GIT PULL')
            elif cond == "reviewed":
                q = Q(properties__name="reviewed",
                      properties__value="true")
            elif cond in ("obsoleted", "old"):
                q = Q(properties__name="obsoleted-by",
                      properties__value__isnull=False) & \
                    ~Q(properties__name="obsoleted-by",
                      properties__value__iexact='')
            elif cond == "applied":
                q = Q(properties__name="git.tag",
                      properties__value__isnull=False) & \
                    ~Q(properties__name="git.tag",
                      properties__value__iexact='')
            elif cond == "tested":
                q = Q(properties__name="testing.done",
                      properties__value="true")
            elif cond == "merged":
                q = Q(is_merged=True)
            else:
                q = as_keywords(term)
            if lneg:
                neg = not neg
        elif term.startswith("has:"):
            cond = term[term.find(":") + 1:]
            if cond == "replies":
                q = Q(last_comment_date__isnull=False)
            else:
                q = Q(properties__name=cond)
        elif term.startswith("project:"):
            cond = term[term.find(":") + 1:]
            self._projects.add(cond)
            q = Q(project__name=cond) | Q(project__parent_project__name=cond)
        else:
            # Keyword in subject is the default
            q = as_keywords(term)
        if neg:
            return query.exclude(pk__in=query.filter(q))
        else:
            return query.filter(q)

    def last_keywords(self):
        return getattr(self, "_last_keywords", [])

    def project(self):
        return next(iter(self._projects)) if len(self._projects) == 1 else None

    def search_series(self, *terms, queryset=None):
        self._last_keywords = []
        self._projects = set()
        if queryset is None:
            queryset = Message.objects.series_heads()
        for t in terms:
            queryset = self._process_term(queryset, t)
        return queryset

    def _process_age_term(self, query, cond):
        import datetime
        def human_to_seconds(n, unit):
            if unit == "d":
                return n * 86400
            elif unit == "w":
                return n * 86400 * 7
            elif unit == "m":
                return n * 86400 * 30
            elif unit == "y":
                return n * 86400 * 365
            raise Exception("No unit specified")

        if cond.startswith("<"):
            less = True
            cond = cond[1:]
        elif cond.startswith(">"):
            less = False
            cond = cond[1:]
        else:
            less = False
        num, unit = cond[:-1], cond[-1].lower()
        if not num.isdigit() or not unit in "dwmy":
            raise InvalidSearchTerm("Invalid age string: %s" % cond)
        sec = human_to_seconds(int(num), unit)
        p = datetime.datetime.now() - datetime.timedelta(0, sec)
        if less:
            q = Q(date__gte=p)
        else:
            q = Q(date__lte=p)
        return q
