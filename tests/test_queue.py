#!/usr/bin/env python3
#
# Copyright 2017 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import sys
import os
sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main
import json
import tempfile
import shutil
import subprocess
from api.models import Message

class QueueTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.add_project("QEMU", "qemu-devel@nongnu.org")

    def cleanUp(self):
        shutil.rmtree(self.repo)

    def test_empty(self):
        self.check_cli(["queues"])

    def test_add(self):
        self.check_cli(["queues", "add", "QEMU", "test-queue"])
        self.check_cli(["queues"], stdout="[QEMU] test-queue")
        self.check_cli(["queues", "add", "QEMU", "test-queue2"])
        self.check_cli(["queues"],
                       stdout=["[QEMU] test-queue", "[QEMU] test-queue2"])

    def test_del(self):
        self.check_cli(["queues", "add", "QEMU", "test-queue"])
        self.check_cli(["queues", "del", "QEMU", "test-queue"])
        self.check_cli(["queues"], stdout="")

    def test_add_patch(self):
        self.check_cli(["import",
                        self.get_data_path("0004-multiple-patch-reviewed.mbox.gz")])
        self.check_cli(["queues", "add", "QEMU", "test-queue"])
        self.check_cli(["queue", "QEMU", "test-queue",
                        "1469192015-16487-1-git-send-email-berrange@redhat.com"])
        self.check_cli(["queues", "show", "QEMU", "test-queue"], stdout=\
                       ["[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption",
                        "[Qemu-devel] [PATCH v4 2/2] block: export LUKS specific data to qemu-img info"])

    def test_del_series(self):
        self.check_cli(["import",
                        self.get_data_path("0004-multiple-patch-reviewed.mbox.gz")])
        self.check_cli(["queues", "add", "QEMU", "test-queue"])
        self.check_cli(["queue", "QEMU", "test-queue",
                        "1469192015-16487-1-git-send-email-berrange@redhat.com"])
        self.check_cli(["drop", "QEMU", "test-queue",
                        "1469192015-16487-1-git-send-email-berrange@redhat.com"])
        self.check_cli(["queues", "show", "QEMU", "test-queue"], stdout="")

    def test_del_patch(self):
        self.check_cli(["import",
                        self.get_data_path("0004-multiple-patch-reviewed.mbox.gz")])
        self.check_cli(["queues", "add", "QEMU", "test-queue"])
        self.check_cli(["queue", "QEMU", "test-queue",
                        "1469192015-16487-1-git-send-email-berrange@redhat.com"])
        self.check_cli(["drop", "QEMU", "test-queue",
                        "1469192015-16487-2-git-send-email-berrange@redhat.com"])
        self.check_cli(["queues", "show", "QEMU", "test-queue"],
                        stdout="[Qemu-devel] [PATCH v4 2/2] block: export LUKS specific data to qemu-img info")

    def test_auto_prop(self):
        self.check_cli(["queues", "add", "QEMU", "test-queue", "prop1", "prop2=val2", "prop3"])
        self.check_cli(["import",
                        self.get_data_path("0004-multiple-patch-reviewed.mbox.gz")])
        self.check_cli(["queue", "QEMU", "test-queue",
                        "1469192015-16487-1-git-send-email-berrange@redhat.com"])
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.get_property("prop1"), "1")
        self.assertEqual(s.get_property("prop2"), "val2")
        self.assertEqual(s.get_property("prop3"), "1")
        m = Message.objects.get(message_id="1469192015-16487-2-git-send-email-berrange@redhat.com")
        self.assertEqual(m.get_property("prop1"), "1")
        self.assertEqual(m.get_property("prop2"), "val2")
        self.assertEqual(m.get_property("prop3"), "1")
        self.check_cli(["drop", "QEMU", "test-queue",
                        "1469192015-16487-2-git-send-email-berrange@redhat.com"])
        m = Message.objects.get(message_id="1469192015-16487-2-git-send-email-berrange@redhat.com")
        self.assertTrue("prop1" not in m.get_properties())
        self.assertTrue("prop2" not in m.get_properties())
        self.assertTrue("prop3" not in m.get_properties())

if __name__ == '__main__':
    main()
