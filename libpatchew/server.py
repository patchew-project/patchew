#!/usr/bin/env python2
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Fam Zheng <famcool@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import bottle
import time
import hmac
import json
from libpatchew import DB, Message, MessageDuplicated, search_doctext, hook

SERVER_VERSION = 1

def render_patch(db, p):
    fr = p.get_from()
    r = {
        'author'         : fr[0],
        'author-address' : fr[1],
        'repliers'       : p.get_status('repliers'),
        'message-id'     : p.get_message_id(),
        'subject'        : p.get_subject(),
        }
    return r

def render_series(db, s, patches=False):
    fr = s.get_from()
    revby = s.get_status('reviewed-by')
    testing = s.get_status('testing', {})
    r = {
        'age'                  : "%d %s" % s.get_age(),
        'author'               : fr[0],
        'author-address'       : fr[1],
        'date'                 : s.get_date(timestamp=True),
        'last-update'          : s.get_status('last-activity-type'),
        'message-id'           : s.get_message_id(),
        'subject'              : s.get_subject(),
        'merged'               : s.get_status('merged'),
        'repliers'             : s.get_status('repliers'),
        'reviewed'             : s.is_reviewed(),
        'reviewers'            : s.get_status('reviewers'),
        'testing-passed'       : testing.get('passed'),
        'testing-end-time'     : testing.get('end-time'),
        'testing-start-time'   : testing.get('start-time'),
        'testing-started'      : testing.get('started'),
        'testing-failure-step' : testing.get('failure-step'),
        'testing-has-warning'  : testing.get('has-warning'),
        }
    if patches:
        r['patches'] = [render_patch(db, x) for x in db.get_patches(s)]
    ob = s.get_status('obsoleted-by')
    if ob:
        ob_series = db.get_message(ob)
        if ob_series:
            r['obsoleted-by-subject'] = ob_series.get_subject()
            r['obsoleted-by'] = ob
    return r

app = bottle.Bottle()

@app.route('/series/<message_id>')
def view_series(message_id):
    """TODO"""
    db = app.db
    s = db.get_series(message_id)
    if not s:
        raise bottle.HTTPError(404)
    return bottle.template("templates/series.tpl", series=s)

@app.route('/series/<message_id>/mbox')
def view_series_mbox(message_id):
    """Return the mbox"""
    db = app.db
    s = db.get_series(message_id)
    if not s:
        raise bottle.HTTPError(404)
    r = s.mbox()
    for p in db.get_patches(s):
        if p.get_message_id() == s.get_message_id():
            continue
        r += p.mbox()
    bottle.response.body = r
    bottle.response.content_type = "text/plain"
    return bottle.response

@app.route('/testing/log/<message_id>')
def view_testing_log(message_id):
    db = app.db
    s = db.get_series(message_id)
    if not s:
        raise bottle.HTTPError(404)
    return bottle.template('templates/testing-log.tpl',
                           series=render_series(db, s, True),
                           log=s.get_status("testing",{}).get("log"))

@app.route('/testing/report', method="POST")
def view_testing_report():
    db = app.db
    forms = bottle.request.forms
    if forms['version'] != str(SERVER_VERSION):
        raise bottle.HTTPError(400, 'Unknown version ' + forms.get('version'))
    data = forms['data']
    identity = forms['identity']
    signature = forms['signature']
    key = db.get_key(identity)
    if not key:
        raise bottle.HTTPError(400, 'Unknown identity ' + identity)
    hasher = hmac.new(key, data)
    if hasher.hexdigest() != signature:
        raise bottle.HTTPError(400, 'Invalid signature')

    result = json.loads(data)
    message_id = result["message-id"]

    test_passed = result['passed']
    failure_step = result["failure-step"]

    s = db.get_series(message_id)
    data = {
        'passed': test_passed,
        'ended': True,
        'end-time': time.time(),
        'log': result['log'],
        'merged': result['merged'],
        'has-warning': '<<< WARNING >>>' in result['log'],
        'failure-step': failure_step,
        }

    db.set_status(s.get_message_id(), 'testing', data)
    hook.invoke("post-testing", **data)
    return {'ok': True}

def next_series_to_test(db):
    """Find the next series for testing"""
    testing_series = None
    candidate = None, None
    candidate_start_time = None
    for s in db.find_series():
        testing = s.get_status('testing', {})
        if testing.get("ended"):
            continue
        patches = db.get_patches(s)
        if len(patches) < s.get_patch_num():
            continue
        if not testing.get("started"):
            # This one is not started yet, start it
            return s, patches
        # Testing is started, but make it a candidate and return if there's no
        # unstarted ones
        if not candidate_start_time or testing.get("start-time") < candidate_start_time:
            candidate = s, patches
            candidate_start_time = testing.get("start-time")
    return candidate

@app.route('/testing/next')
def view_testing_next():
    db = app.db
    s, patches = next_series_to_test(db)
    r = {}
    r['version'] = SERVER_VERSION
    if s:
        r['has-data']                = True
        r['message-id']              = s.get_message_id()
        r['series-subject']          = s.get_subject(strip_tags=True)
        r['patches-message-id-list'] = [x.get_message_id(strip_angle_brackets = True) for x in patches]
        r['patches-mbox-list']       = [x.mbox() for x in patches]
        r['codebase'], r['branch']   = s.get_codebase()
        db.set_status(s.get_message_id(), "testing", {
            'started': True,
            'start-time': time.time(),
            })
        hook.invoke("pre-testing", **r)
    else:
        r['has-data'] = False
    return r

def render_message(db, m):
    fr = m.get_from()
    subject = m.get_subject()
    vs = subject
    irt = m.get_in_reply_to()
    if irt:
        rm = db.get_message(irt)
        if rm:
            vs = m.get_subject(suppress_re=rm.get_subject())

    return {'subject': subject,
            'visible-subject': vs,
            'author': fr[0],
            'author-address': fr[1],
            'date': m.get_date(timestamp=True),
            'age': "%d %s" % m.get_age(),
            'body': m.get_body(),
            'preview': m.get_preview(),
            'message-id': m.get_message_id(),
            'replies': [render_message(db, x) for x in db.get_replies(m)],
            }

@app.route("/series/<message_id>")
def view_thread(message_id):
    db = app.db
    thread = render_message(db, db.get_message(message_id))
    return bottle.template("templates/thread.tpl", thread=thread)

@app.route('/')
@app.route('/index')
@app.route('/index/')
@app.route('/index/<start>-<end>')
def view_index(start=0, end=50):
    db = app.db
    pagesize = 100
    start = int(start)
    end = int(end)
    limit = min(pagesize, end - start)
    curpage = int((start - 1) / pagesize) + 1
    query = bottle.request.query.get("search")
    totalpages = (db.find_series_count(query=query) - 1) / pagesize + 1
    series = [render_series(db, x) for x in db.find_series(query=query, skip=start, limit=limit)]
    return bottle.template("templates/series-index.tpl",
                           series=series,
                           totalpages=totalpages,
                           curpage=curpage,
                           pagesize=pagesize,
                           search=query,
                           search_help=search_doctext)

@app.route('/favicon.ico')
@app.route('/static/<filename>')
def server_static(filename='favicon.ico'):
    root = '/usr/share/patchew/static'
    if os.path.isdir('static'):
        root = 'static'
    return bottle.static_file(filename, root=root)

def start_server(db, **args):
    bottle.TEMPLATE_PATH.append('/usr/share/patchew')
    app.db = db
    app.run(**args)
