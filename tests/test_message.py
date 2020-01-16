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

    def test_0_second(self):
        message = Message()
        message.date = datetime.datetime.utcnow()
        age = message.get_age()
        self.assertEqual(age, "0 second")

    def test_now(self):
        message = Message()
        dt = datetime.datetime.fromtimestamp(time.time() + 100)
        message.date = dt
        age = message.get_age()
        self.assertEqual(age, "now")

    def test_1_day(self):
        message = Message()
        dt = datetime.datetime.fromtimestamp(time.time() - 3600 * 25)
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


if __name__ == "__main__":
    main()
