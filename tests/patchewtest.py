#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import unittest
import subprocess
import sys
import os
import tempfile
import time
import shutil
import argparse

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

RUN_DIR = tempfile.mkdtemp()
_logf = open(os.path.join(RUN_DIR, "log"), "w")

class PatchewTestCase(unittest.TestCase):
    server_port = 18383
    server_url = "http://127.0.0.1:%d/" % server_port
    manage_py = os.path.join(BASE_DIR, "manage.py")
    patchew_cli = os.path.join(BASE_DIR, "patchew-cli")
    superuser = "test"
    password = "patchewtest"

    def assert_server_running(self):
        return self._server_p.poll() == None

    def start_server(self):
        os.environ["PATCHEW_DATA_DIR"] = tempfile.mkdtemp(dir=RUN_DIR,
                                                          prefix="data-")
        subprocess.check_output([self.manage_py, "migrate"])
        self.create_user(self.superuser, self.password, True)
        self._server_p = subprocess.Popen([self.manage_py, "runserver",
                                           "--noreload",
                                           str(self.server_port)],
                                          stdout=_logf, stderr=_logf)
        ok = False
        for i in range(20):
            devnull = open("/dev/null", "w")
            rc = subprocess.call(["curl", self.server_url],
                                 stdout=devnull, stderr=devnull)
            if rc == 0:
                ok = True
                break
            time.sleep(0.05)
        self.assertTrue(ok)
        self.assert_server_running()

    def create_user(self, username, password, is_superuser=False, groups=[]):
        p = subprocess.Popen([self.manage_py, "shell"],
                             stdin=subprocess.PIPE, stdout=_logf,
                             stderr=_logf)
        p.stdin.write("from django.contrib.auth.models import User, Group\n")
        p.stdin.write("user=User.objects.create_user('%s', password='%s')\n" % \
                      (username, password))
        p.stdin.write("user.is_superuser=%s\n" % is_superuser)
        p.stdin.write("user.is_staff=True\n")
        if groups:
            groups_str = ", ".join('"%s"' % s for s in groups)
            p.stdin.write("user.groups = [Group.objects.get(name=x) for x in [%s]]\n" \
                          % groups_str)
        p.stdin.write("user.save()\n")
        p.stdin.close()
        p.wait()

    def stop_server(self):
        self._server_p.terminate()

    def cli_command(self, *argv):
        """Run patchew-cli command and return (retcode, stdout, stderr)"""
        p = subprocess.Popen([self.patchew_cli, "-D", "-s", self.server_url] +\
                              list(argv),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        a, b = p.communicate()
        return p.returncode, a.strip(), b.strip()

    def check_cli_command(self, *argv):
        r, a, b = self.cli_command(*argv)
        if r != 0:
            print a
            print b
            self.assertEqual(r, 0)
        return a, b

    def login(self, username=None, password=None):
        if not username:
            username = self.superuser
        if not password:
            password = self.password
        r, a, b = self.cli_command("login", username, password)
        self.assertEqual(r, 0)

    def logout(self):
        r, a, b = self.cli_command("logout")
        self.assertEqual(r, 0)

    def get_data_path(self, fname):
        r = tempfile.NamedTemporaryFile(dir=RUN_DIR, prefix="test-data-",
                                        delete=False)
        d = os.path.join(BASE_DIR, "tests", "data", fname)
        r.write(subprocess.check_output(["zcat", d]))
        r.close()
        return r.name

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Enable debug output, and keep temp dir after done")
    return parser.parse_known_args()

def main():
    args, argv = parse_args()
    if args.debug:
        print RUN_DIR
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
