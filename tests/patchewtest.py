#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import subprocess
import sys
import os
import tempfile
import shutil
import argparse
import json

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

sys.path.append(BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "patchew.settings")
import django

django.setup()

import django.test
from django.contrib.auth.models import User, Group
from api.models import *

PATCHEW_CLI = os.path.join(BASE_DIR, "patchew-cli")
RUN_DIR = tempfile.mkdtemp()

class PatchewTestCase(django.test.LiveServerTestCase):
    user = "admin"
    email = "admin@test"
    password = "adminpass"
    client = django.test.Client()

    def create_superuser(self, username=None, password=None):
        user = User.objects.create_superuser(username or self.user,
                                             self.email,
                                             password or self.password)

    def create_user(self, username=None, password=None, groups=[]):
        user = User.objects.create_user(username or self.user,
                                        self.email,
                                        password or self.password)
        if groups:
            user.groups = [Group.objects.get_or_create(name=g)[0] for g in groups]
            user.save()

    def cli(self, argv):
        """Run patchew-cli command and return (retcode, stdout, stderr)"""
        cmd = [PATCHEW_CLI, "-D", "-s", self.live_server_url] + argv
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        a, b = p.communicate()
        a = a.decode("utf-8")
        b = b.decode("utf-8")
        return p.returncode, a.strip(), b.strip()

    def check_cli(self, args, rc=0, stdout=None, stderr=None):
        assert(isinstance(args, list))
        r, a, b = self.cli(args)
        self.assertEqual(r, rc,
            "Exit code {} != expected {}, stdout:\n{}\nstderr:\n{}\n".format(r, rc, a, b))
        if stdout:
            self.assertEqual(a, stdout)
        if stderr:
            self.assertEqual(b, stderr)
        return a, b

    def cli_login(self, username=None, password=None):
        if not username:
            username = self.user
        if not password:
            password = self.password
        self.check_cli(["login", username or self.user, password or self.password])

    def cli_logout(self):
        self.check_cli(["logout"])

    def get_data_path(self, fname):
        r = tempfile.NamedTemporaryFile(dir=RUN_DIR, prefix="test-data-", delete=False)
        d = os.path.join(BASE_DIR, "tests", "data", fname)
        r.write(subprocess.check_output(["zcat", d]))
        r.close()
        return r.name

    def get_projects(self):
        return Project.objects.all()

    def add_project(self, name, mailing_list=""):
        p = Project(name=name, mailing_list=mailing_list)
        p.save()

    def api_login(self):
        r = self.client.login(username=self.user, password=self.password)
        self.assertTrue(r)

    def api_call(self, method, **params):
        resp = self.client.post('/api/%s/' % method, {"params": json.dumps(params)})
        return json.loads(resp.content.decode('utf-8')) if resp.content else None

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Enable debug output, and keep temp dir after done")
    return parser.parse_known_args()

def main():
    import unittest
    args, argv = parse_args()
    if args.debug:
        print(RUN_DIR)
    try:
        if args.debug:
            verbosity = 2
        else:
            verbosity = 1
        return unittest.main(argv=[sys.argv[0]] + argv,
                             verbosity=verbosity)
    finally:
        if not args.debug:
            shutil.rmtree(RUN_DIR)

