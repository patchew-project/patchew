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
import atexit
import gzip

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

sys.path.append(BASE_DIR)

os.environ["PATCHEW_TEST"] = "1"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "patchew.settings")
import django

django.setup()

import django.test
from django.contrib.auth.models import User, Group
import rest_framework.test
from api.models import *

PATCHEW_CLI = os.path.join(BASE_DIR, "patchew-cli")
RUN_DIR = tempfile.mkdtemp()
os.environ["PATCHEW_TEST_DATA_DIR"] = os.path.join(RUN_DIR, "patchew-data")

class PatchewTestCase(django.test.LiveServerTestCase):
    user = "admin"
    email = "admin@test"
    password = "adminpass"
    client = django.test.Client()
    api_client = rest_framework.test.APIClient()

    REST_BASE = 'http://testserver/api/v1/'

    def get_tmpdir(self):
        if not hasattr(self, "_tmpdir"):
            self._tmpdir = tempfile.mkdtemp()
            atexit.register(shutil.rmtree, self._tmpdir)
        return self._tmpdir

    def create_superuser(self, username=None, password=None):
        user = User.objects.create_superuser(username or self.user,
                                             self.email,
                                             password or self.password)
        return user

    def create_user(self, username=None, password=None, groups=[]):
        user = User.objects.create_user(username or self.user,
                                        self.email,
                                        password or self.password)
        if groups:
            user.groups = [Group.objects.get_or_create(name=g)[0] for g in groups]
            user.save()
        return user

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
        if stdout is not None:
            self.assertEqual(stdout, a)
        if stderr is not None:
            self.assertEqual(stderr, b)
        return a, b

    def cli_login(self, username=None, password=None):
        if not username:
            username = self.user
        if not password:
            password = self.password
        self.check_cli(["login", username or self.user, password or self.password])

    def cli_logout(self):
        self.check_cli(["logout"])

    def cli_import(self, mbox, rc=0):
        self.check_cli(["import", self.get_data_path(mbox)], rc)

    def get_data_path(self, fname):
        r = tempfile.NamedTemporaryFile(dir=RUN_DIR, prefix="test-data-", delete=False)
        d = os.path.join(BASE_DIR, "tests", "data", fname)
        with gzip.open(d, 'rb') as f:
            file_content = f.read()
        r.write(file_content)
        r.close()
        return r.name

    def get_projects(self):
        return Project.objects.all()

    def add_project(self, name, mailing_list="", git_repo=""):
        p = Project(name=name, mailing_list=mailing_list, git=git_repo)
        p.save()
        return p

    def api_login(self):
        r = self.client.login(username=self.user, password=self.password)
        self.assertTrue(r)

    def api_call(self, method, **params):
        resp = self.client.post('/api/%s/' % method, {"params": json.dumps(params)})
        return json.loads(resp.content.decode('utf-8')) if resp.content else None

    def apply_and_retrieve(self, mbox, project_id, msgid):
        # TODO: change this to a REST import when it is added
        self.cli_login()
        self.cli_import(mbox)
        self.cli_logout()

        response = self.api_client.get('%sprojects/%d/series/%s/' % (self.REST_BASE, project_id, msgid))
        if response.status_code == 200:
            uri = response.data['resource_uri']
            self.assertEqual(uri, '%sprojects/%d/series/%s/' % (self.REST_BASE, project_id, msgid))
        return response

    def create_git_repo(self, name="test-repo"):
        repo = os.path.join(self.get_tmpdir(), name)
        os.mkdir(repo)
        subprocess.check_output(["git", "init"], cwd=repo)
        subprocess.check_output(["touch", "foo"], cwd=repo)
        subprocess.check_output(["git", "add", "foo"], cwd=repo)
        subprocess.check_output(["git", "commit", "-m", "initial commit"],
                                cwd=repo)
        return repo

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

