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
        self.cli_login()
        p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        p.prefix_tags = "!qemu-web"
        p.save()

    def test_import_one(self):
        self.check_cli(["import", self.get_data_path("0017-qemu-web-is-not-qemu.mbox.gz")])
        self.check_cli(["search"], stdout='')

if __name__ == '__main__':
    main()
