#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
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
        self.add_project("QEMU", "qemu-devel@nongnu.org")

    def test_import_one(self):
        self.check_cli(["import", self.get_data_path("0001-simple-patch.mbox.gz")])
        self.check_cli(["search"],
                       stdout='[Qemu-devel] [PATCH] quorum: Only compile when supported')

    def test_import_belong_to_multiple_projects(self):
        self.check_cli(["project", "add", "QEMU2",
                       "--mailing-list", "qemu-devel@nongnu.org"])
        self.check_cli(["import",
                        self.get_data_path("0001-simple-patch.mbox.gz")])
        a = '[Qemu-devel] [PATCH] quorum: Only compile when supported\n' * 2
        self.check_cli(["search"], stdout=a.strip())

    def test_case_insensitive(self):
        self.check_cli(["import",
                       self.get_data_path("0002-unusual-cased-tags.mbox.gz")])
        a, b = self.check_cli(["search", "-r"])
        ao = json.loads(a)[0]
        self.assertEqual(["Fam Zheng", "famz@redhat.com"],
                         ao["properties"]["reviewers"][0])
        self.assertIn('Reviewed-By: Fam Zheng <famz@redhat.com>',
                      ao["properties"]["tags"])
        self.assertIn('tESTed-bY: Fam Zheng <famz@redhat.com>',
                      ao["properties"]["tags"])

    def test_non_utf_8(self):
        self.check_cli(["import",
                       self.get_data_path("0005-non-utf-8.mbox.gz")])

    def test_non_utf_8_multiplart(self):
        self.check_cli(["import",
                       self.get_data_path("0006-multi-part-non-utf-8.mbox.gz")])

    def test_import_invalid_charset(self):
        self.check_cli(["import",
                       self.get_data_path("0007-invalid-charset.mbox.gz")])

    def test_obsoleted_by(self):
        self.check_cli(["import",
                       self.get_data_path("0009-obsolete-by.mbox.gz")])
        a, b = self.check_cli(["search", "-r"])
        ao = json.loads(a)
        for m in ao:
            if "[PATCH]" in m["subject"]:
                self.assertTrue(m["properties"].get("obsoleted-by"))
            else:
                self.assertFalse(m["properties"].get("obsoleted-by"))

class UnprivilegedImportTest(ImportTest):
    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.check_cli(["project", "add", "QEMU",
                       "--mailing-list", "qemu-devel@nongnu.org"])
        self.cli_logout()
        self.create_user("importer", "importerpass", groups=["importers"])
        self.cli_login("importer", "importerpass")

    test_import_belong_to_multiple_projects = None

    def check_import_should_fail(self):
        self.check_cli(["import",
                       self.get_data_path("0001-simple-patch.mbox.gz")], 1)
        a, b = self.check_cli(["search"])
        self.assertNotIn('[Qemu-devel] [PATCH] quorum: Only compile when supported',
                         a.splitlines())

    def test_anonymous_import(self):
        self.cli_logout()
        self.check_import_should_fail()

    def test_normal_user_import(self):
        self.cli_logout()
        self.create_user("someuser", "somepass")
        self.cli_login("someuser", "somepass")
        self.check_import_should_fail()

if __name__ == '__main__':
    main()
