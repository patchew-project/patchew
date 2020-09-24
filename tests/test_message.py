#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import json
import time
import datetime

from .patchewtest import PatchewTestCase, main

from api.models import Message


class MessageTest(PatchewTestCase):
    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")

    def test_0_second(self):
        message = Message()
        message.date = datetime.datetime.utcnow()
        age = message.get_age()
        self.assertEqual(age, "0 second")

    def test_now(self):
        message = Message()
        dt = datetime.datetime.utcfromtimestamp(time.time() + 100)
        message.date = dt
        age = message.get_age()
        self.assertEqual(age, "now")

    def test_1_day(self):
        message = Message()
        dt = datetime.datetime.utcfromtimestamp(time.time() - 3600 * 25)
        message.date = dt
        age = message.get_age()
        self.assertEqual(age, "1 day")

    def test_asctime(self):
        message = Message()
        dt = datetime.datetime(2016, 10, 22, 10, 16, 40)
        message.date = dt
        asctime = message.get_asctime()
        self.assertEqual(asctime, "Sat Oct 22 10:16:40 2016")

        message = Message()
        dt = datetime.datetime(2016, 10, 22, 9, 6, 4)
        message.date = dt
        asctime = message.get_asctime()
        self.assertEqual(asctime, "Sat Oct 22 9:06:04 2016")

    def test_topic_on_series_head(self):
        self.cli_login()
        self.cli_import("0004-multiple-patch-reviewed.mbox.gz")
        m1 = Message.objects.get(
            message_id="1469192015-16487-1-git-send-email-berrange@redhat.com"
        )
        assert m1.is_series_head
        assert m1.topic is not None
        m2 = Message.objects.get(
            message_id="1469192015-16487-2-git-send-email-berrange@redhat.com"
        )
        assert not m2.is_series_head
        assert m2.topic is None

    def test_topic_assignment(self):
        self.cli_login()
        self.cli_import("0004-multiple-patch-reviewed.mbox.gz")
        self.cli_import("0009-obsolete-by.mbox.gz")

        m1 = Message.objects.get(message_id="20160628014747.20971-1-famz@redhat.com")
        m2 = Message.objects.get(message_id="20160628014747.20971-2-famz@redhat.com")
        m3 = Message.objects.get(message_id="20160628014747.20971-3-famz@redhat.com")
        self.assertEqual(m1.topic, m2.topic)
        self.assertEqual(m1.topic, m3.topic)
        n = Message.objects.get(
            message_id="1469192015-16487-1-git-send-email-berrange@redhat.com"
        )
        self.assertNotEqual(m1.topic, n.topic)


if __name__ == "__main__":
    main()
