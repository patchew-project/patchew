#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from .models import Message, MessageResult, Result, QueuedSeries
from collections import namedtuple
from functools import reduce
import operator

from django.db import connection
from django.db.models import Q

from django.contrib.postgres.search import SearchQuery, SearchVector, SearchVectorField
from django.db.models import Lookup
from django.db.models.fields import Field

import abc
import compynator.core

@Field.register_lookup
class NotEqual(Lookup):
    lookup_name = "ne"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return "%s <> %s" % (lhs, rhs), params


class InvalidSearchTerm(Exception):
    pass


# Hack alert: Django wraps each argument to to_tsvector with a COALESCE function,
# and that causes postgres not to use the index.  Monkeypatch as_sql to skip
# that step, which we do not need since the subject field is not nullable.
class NonNullSearchVector(SearchVector):
    function = "to_tsvector"
    arg_joiner = " || ' ' || "
    _output_field = SearchVectorField()

    def as_sql(self, compiler, connection, function=None, template=None):
        config_sql = None
        config_params = []
        if template is None:
            if self.config:
                config_sql, config_params = compiler.compile(self.config)
                template = '%(function)s(%(config)s, %(expressions)s)'
            else:
                template = self.template
        sql, params = super(SearchVector, self).as_sql(
            compiler, connection, function=function, template=template,
            config=config_sql,
        )
        extra_params = []
        if self.weight:
            weight_sql, extra_params = compiler.compile(self.weight)
            sql = 'setweight({}, {})'.format(sql, weight_sql)
        return sql, config_params + params + extra_params


# The abstract syntax tree of the search.  This allows:
# - showing the project name if the result of the search is a single project
# - highlighting all keywords
# - using a single SearchVector for multiple ANDed keywords
#
# On top of this, SearchMaint and SearchQueue allow to use a singleton parser
# that does not know about requests, and only resolve the user ("me") later

class SearchExpression(metaclass=abc.ABCMeta):
    def get_project(self):
        return None

    def get_all_keywords(self):
        return self.get_keywords()

    def get_keywords(self):
        return []

    @abc.abstractmethod
    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        pass

    def get_query(self, user, keyword_map, keyword_final):
        # Combine the query returned by get_query_no_keywords()
        # with the keyword search for the result of get_keywords()
        query_no_kw = self.get_query_no_keywords(user, keyword_map, keyword_final)
        kw = self.get_keywords()
        if not kw:
            return query_no_kw
        query_kw = reduce(operator.and_, map(keyword_map, self.get_keywords()))
        return query_no_kw & keyword_final(query_kw)

    def __invert__(self):
        return SearchNot(self)

    def __or__(self, rhs):
        if isinstance(rhs, SearchFalse):
            return self
        return SearchOr(self, rhs)

    def __and__(self, rhs):
        if isinstance(rhs, SearchTrue):
            return self
        return SearchAnd(self, rhs)


class SearchFalse(SearchExpression):
    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        return Q(pk=None)

    def __invert__(self):
        return SearchTrue(self)

    def __or__(self, rhs):
        return rhs


class SearchTrue(SearchExpression):
    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        return Q()

    def __invert__(self):
        return SearchFalse(self)

    def __and__(self, rhs):
        return rhs


class SearchNot(SearchExpression, namedtuple('SearchNot', ['op'])):
    def get_all_keywords(self):
        return self.op.get_all_keywords()

    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        return ~self.op.get_query(user, keyword_map, keyword_final)

    def __invert__(self):
        return self.op


class SearchBinary(SearchExpression, namedtuple('SearchBinary', ['left', 'right'])):
    def get_all_keywords(self):
        return self.left.get_all_keywords() + self.right.get_all_keywords()


class SearchAnd(SearchBinary):
    def get_project(self):
        return self.left.get_project() or self.right.get_project()

    def get_keywords(self):
        return self.left.get_keywords() + self.right.get_keywords()

    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        return self.left.get_query_no_keywords(user, keyword_map, keyword_final) \
                & self.right.get_query_no_keywords(user, keyword_map, keyword_final)


class SearchOr(SearchBinary):
    def get_project(self):
        candidate = self.left.get_project()
        if candidate:
            return candidate if self.right.get_project() == candidate else None
        return None

    def get_keywords(self):
        return []

    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        # keywords from the left and right part cannot be combined in a
        # single query, so resolve them already
        return self.left.get_query(user, keyword_map, keyword_final) \
                | self.right.get_query(user, keyword_map, keyword_final)


class SearchTerm(SearchExpression, namedtuple('SearchTerm', ['project', 'query'])):
    def __invert__(self):
        return SearchTerm(project=None, query=~self.query)

    def get_project(self):
        return self.project

    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        return self.query


class SearchKeyword(SearchExpression, namedtuple('SearchKeyword', ['keyword'])):
    def get_keywords(self):
        return [self.keyword]

    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        return Q()


class SearchSubquery(SearchExpression, namedtuple('SearchQueue', ['model', 'q'])):
    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        message_ids = self.model.objects.filter(self.q).values("message_id")
        return Q(id__in=message_ids)


class SearchQueue(SearchExpression, namedtuple('SearchQueue', ['queues', 'username'])):
    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        if self.username == "me":
            if not user.is_authenticated:
                # Django hack to return an always false Q object
                return Q(pk=None)
            q = Q(user=user, name__in=self.queues)
        else:
            q = Q(user__username=self.username, name__in=self.queues)
        message_ids = QueuedSeries.objects.filter(q).values("message_id")
        return Q(id__in=message_ids)

class SearchMaint(SearchExpression, namedtuple('SearchMaint', ['rhs'])):
    def get_query_no_keywords(self, user, keyword_map, keyword_final):
        if self.rhs == "me":
            if not user.is_authenticated:
                # Django hack to return an always false Q object
                return Q(pk=None)
            return Q(maintainers__icontains=user.email)
        else:
            return Q(maintainers__icontains=self.rhs)


def __parser(_Q):
    from compynator.core import One, Terminal
    from compynator.niceties import Digit, Forward, Lookahead

    def Q(**kwargs):
        return SearchTerm(project=None, query=_Q(**kwargs))

    def K(keyword):
        return SearchKeyword(keyword)

    def human_to_seconds(n, unit):
        unit = unit.lower()
        if unit == "d":
            return int(n) * 86400
        elif unit == "w":
            return int(n) * 86400 * 7
        elif unit == "m":
            return int(n) * 86400 * 30
        elif unit == "y":
            return int(n) * 86400 * 365
        raise Exception("No unit specified")

    def _make_filter_age(cond, sec):
        import datetime

        less = cond == "<"
        p = datetime.datetime.now() - datetime.timedelta(0, sec)
        if less:
            q = Q(date__gte=p)
        else:
            q = Q(date__lte=p)
        return q

    def _make_filter_project(cond):
        return SearchTerm(project=cond,
                          query=_Q(project__name=cond) | _Q(project__parent_project__name=cond))

    def _make_filter_is(cond):
        if cond == "complete":
            return Q(is_complete=True)
        elif cond == "pull":
            return K("PULL") & SearchTerm(project=None,
                                          query=_Q(subject__contains="[PULL") | _Q(subject__contains="[GIT PULL"))
        elif cond == "reviewed":
            return Q(is_reviewed=True)
        elif cond in ("obsoleted", "old", "obsolete"):
            return Q(is_obsolete=True)
        elif cond == "applied":
            return SearchSubquery(
                MessageResult, _Q(name="git", status=Result.SUCCESS)
            )
        elif cond == "tested":
            return Q(is_tested=True)
        elif cond == "merged":
            return Q(is_merged=True)
        return None

    def _make_filter_not(cond):
        q = _make_filter_is(cond)
        if q:
            q = ~q
        return q

    def _make_filter_is_or_keyword(cond):
        return _make_filter_is(cond) or K(cond)

    def _make_subquery_result(term, **kwargs):
        q = _Q(name=term, **kwargs) | _Q(name__startswith=term + ".", **kwargs)
        return SearchSubquery(MessageResult, q)

    def _make_filter_result(kind, term):
        if kind == "failure:":
            return _make_subquery_result(term, status=Result.FAILURE)
        if kind == "success:":
            # What we want is "all results are successes", but the only way to
            # express it is "there is a result and not (any result is not a success)".
            return _make_subquery_result(term) & ~_make_subquery_result(
                term, status__ne=Result.SUCCESS
            )
        if kind == "pending:":
            return _make_subquery_result(term, status=Result.PENDING)
        if kind == "running:":
            return _make_subquery_result(term, status=Result.RUNNING)

    def field(terminal, value, field):
        return Terminal(terminal).then(value).value(lambda x: Q(**{ field: x }))

    def charset(cs, reverse=False, lookahead=False):
        if reverse:
            char = One.where(lambda c: c not in cs)
        else:
            char = One.where(lambda c: c in cs)
        if lookahead:
            return Lookahead(char)
        else:
            return char

    WordChar = charset(' \t<>{}()', reverse=True)
    Space = One.where(lambda c: c == ' ' or c == '\t')
    Word = WordChar.repeat(lower=1)
    WordNoColon = Word.filter(lambda x: ':' not in x.value)
    Spaces = Space.repeat(lower=1, reducer=lambda x, y: None)
    RemoveBrackets = Terminal('<').repeat(upper=1).then(Word).skip(Terminal('>').repeat(upper=1))

    Maint = (Terminal('maintained-by:') | Terminal('maint:'))
    ResultOutcome = Terminal('failure:') | Terminal('success:') | Terminal('pending:') | Terminal('running:')
    Ack = (Terminal('ack:') | Terminal('accept:') | Terminal('accepted:')).value(lambda x: ['accept'])
    Nack = (Terminal('nack:') | Terminal('reject:') | Terminal('rejected:')).value(lambda x: ['reject'])
    Review = (Terminal('review:') | Terminal('reviewed:')).value(lambda x: ['accept', 'reject'])

    Timespan = Digit.repeat().then(charset('DWMYdwmy'), human_to_seconds)
    Age = charset('<>').repeat(upper=1).then(Timespan, _make_filter_age)
    AgeTerm = (Terminal('age:') | charset('<>', lookahead=True)).then(Age)

    SimpleFieldTerm = (
            field('from:', Word, 'sender__icontains') |
            field('to:', Word, 'recipients__icontains') |
            field('id:', RemoveBrackets, 'message_id') |
            field('rfcmsg822id:', RemoveBrackets, 'message_id') |
            Terminal('project:').then(Word).value(_make_filter_project) |
            Terminal('subject:').then(Word).value(K) |
            Terminal('queue:').then(Word, lambda _, q: SearchQueue([q], 'me')) |
            Maint.then(Word).value(SearchMaint) |
            (Ack | Nack | Review).then(Word, SearchQueue) |
            ResultOutcome.then(Word, _make_filter_result))

    # _make_filter_is and _make_filter_not return None if the RHS is not accepted
    IsTerm = (
            Terminal('is:').then(Word).value(_make_filter_is) |
            Terminal('not:').then(Word).value(_make_filter_not)) \
        .filter(lambda x: x is not None)

    HasTerm = (
            Terminal('has:replies').value(lambda x: Q(last_comment_date__isnull=False)) |
            field('has:', Word, 'properties__name'))

    Conjunction = Forward()
    Disjunction = Forward()

    BooleanTerm = (AgeTerm |
            SimpleFieldTerm |
            IsTerm |
            HasTerm |
            Conjunction |
            Disjunction)

    # + and - try to match an "is:" condition, and falls back to a keyword
    PlusTerm = Terminal('+').then(
        WordNoColon.value(_make_filter_is_or_keyword) | BooleanTerm)
    MinusTerm = Terminal('-').then(
        WordNoColon.value(_make_filter_is_or_keyword) | BooleanTerm).value(operator.invert)
    BasicTerm = charset('+-!', reverse=True, lookahead=True).then(
        WordNoColon.value(K) | BooleanTerm)
    BangTerm = Terminal('!').then(BasicTerm).value(operator.invert)

    AnyTerm = PlusTerm | MinusTerm | BangTerm | BasicTerm

    Rest = Spaces.then(AnyTerm).repeat(value=SearchFalse(), reducer=operator.or_)
    DisjunctionTerms = AnyTerm.then(Rest, reducer=operator.or_)

    Rest = Spaces.then(AnyTerm).repeat(value=SearchTrue(), reducer=operator.and_)
    ConjunctionTerms = AnyTerm.then(Rest, reducer=operator.and_)

    Disjunction.is_(Terminal('{').then(DisjunctionTerms).skip(Terminal('}')))
    Conjunction.is_(Terminal('(').then(ConjunctionTerms).skip(Terminal(')')))
    return ConjunctionTerms

def parse(s, the_parser=__parser(Q)):
    results = the_parser(s)
    if not isinstance(results, compynator.core.Success):
        #raise Exception("invalid search terms at '" + s + "'")
        return SearchFalse()
    result = next(iter(results))
    if result.remain:
        #raise Exception("invalid search terms at '" + result.remain + "'")
        return SearchFalse()
    return result.value


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
 - is:obsolete, is:obsoleted, is:old - the series has newer version
 - is:complete - the series has all the patches it contains
 - is:merged - the series is included in the project's git tree
 - is:pull - the series is a pull request
 - is:applied - a git tree is available for the series
 - has:replies - the series received a reply (apart from patches sent by the submitter)

Example:

    is:reviewed

"not:X" is the opposite of "is:X". "+X" and "-X" are shorter synonyms of "is:X"
and "not:X" respectively.

---

### Search addresses

 - Syntax: from:ADDRESS
 - Syntax: to:ADDRESS

Compare the address info of message. Example:

    from:alice to:bob

---

### Search by maintainer associated with the changeset

 - Syntax: maintained-by:NAME
 - Syntax: maint:NAME

NAME can be the name, email or a substring of MAINTAINERS file entries of the
maintainer.

---

### Search by result

Syntax:

 - pending:NAME, failure:NAME, running:NAME - any result with the given
   name is in the pending/failure/running state
 - success:NAME - all results with the given name are in the success state
   (and there is at least one result with the given name)

where NAME can be e.g. "git", "testing", "testing.TEST-NAME"

Example:

    success:git
    failure:testing.FreeBSD

---

### Search by review state

Syntax:

 - accept:USERNAME or ack:USERNAME - the series was marked as accepted by the user
 - reject:USERNAME or nack:USERNAME - the series was marked as reject by the user
 - review:USERNAME - the series was marked as accepted or rejected by the user
 - watch:USERNAME - the series is in the user's watched queue
 - queue:NAME - the series is in the given queue of the current user

USERNAME can be "me" to identify the current user

---

### Reverse condition

 - Syntax: !TERM

Negative of an expression. Example:

    !is:reviewed     (query series that are not reviewed)
    !has:replies     (query series that have not received any comment)

---

### Search by message id

 - Syntax: id:MESSAGE-ID
 - Syntax: rfc822msgid:MESSAGE-ID

Exact match of message-id. Example:

    id:<1416902879-17422-1-git-send-email-user@domain.com>

or

    id:1416902879-17422-1-git-send-email-user@domain.com

The two prefixes are equivalent.

---

### Search by text

 - Syntax: KEYWORD

Search text keyword in the email message. Example:

    regression

---

### AND and OR

- Syntax: { TERM TERM }
- Syntax: ( TERM TERM )

Alternatives can be written within braces.  The query will match
if at least one of the terms matches.

AND is usually obtained just by writing terms next to each other,
except inside braces.  For this reason you can also explicitly write
an "AND" using parentheses.
"""

    def __init__(self, terms, user):
        self.q = reduce(
            operator.and_, map(lambda t: parse(t), terms))
        self.user = user

    def last_keywords(self):
        return self.q.get_all_keywords()

    def project(self):
        return self.q.get_project()

    def search_series(self, queryset=None):
        if queryset is None:
            queryset = Message.objects.series_heads()

        if connection.vendor == "postgresql":
            have_keywords = len(self.q.get_all_keywords()) > 0
            if have_keywords:
                queryset = queryset.annotate(
                    subjsearch=NonNullSearchVector("subject", config="english")
                )
            q = self.q.get_query(self.user,
                        lambda x: SearchQuery(x, config="english"),
                        lambda x: Q(subjsearch=x))
        else:
            q = self.q.get_query(self.user,
                        lambda x: Q(subject__icontains=x),
                        lambda x: x)

        return queryset.filter(q)

    def query_test_message(self, message):
        queryset = Message.objects.filter(id=message.id)
        return self.search_series(queryset=queryset).first()
