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

class ImportTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.p.prefix_tags = "!qemu-web"
        self.p.save()

    def test_import_one(self):
        resp = self.apply_and_retrieve('0017-qemu-web-is-not-qemu.mbox.gz',
                                       self.p.id, '1504250391-6353-1-git-send-email-thuth@redhat.com')
        self.assertEquals(resp.status_code, 404)

if __name__ == '__main__':
    main()
