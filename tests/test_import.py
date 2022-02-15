#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.


from api.models import Message, Project

from .patchewtest import PatchewTestCase, main


class ImportTest(PatchewTestCase):
    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.add_project("QEMU", "qemu-devel@nongnu.org")

    def test_import_one(self):
        self.cli_import("0001-simple-patch.mbox.gz")
        self.check_cli(
            ["search"],
            stdout="[Qemu-devel] [PATCH] quorum: Only compile when supported",
        )

    def test_import_belong_to_multiple_projects(self):
        self.check_cli(
            ["project", "add", "QEMU2", "--mailing-list", "qemu-devel@nongnu.org"]
        )
        self.cli_import("0001-simple-patch.mbox.gz")
        a = "[Qemu-devel] [PATCH] quorum: Only compile when supported\n" * 2
        self.check_cli(["search"], stdout=a.strip())

    def test_non_utf_8(self):
        self.cli_import("0005-non-utf-8.mbox.gz")

    def test_non_utf_8_multiplart(self):
        self.cli_import("0006-multi-part-non-utf-8.mbox.gz")

    def test_import_invalid_charset(self):
        self.cli_import("0007-invalid-charset.mbox.gz")

    def test_import_invalid_byte(self):
        self.add_project("EDK2", "edk2-devel@lists.01.org")
        self.cli_import("0010-invalid-byte.mbox.gz")
        self.check_cli(
            ["search"],
            stdout='[edk2] [PATCH 0/3] Revert "ShellPkg: Fix echo to support displaying special characters"',
        )

    def test_import_to_subproject(self):
        tp = self.add_project(
            "Libvirt",
            "libvir-list@redhat.com, libvirt-list@redhat.com",
            "git://libvirt.org/libvirt.git",
        )
        tp.prefix_tags = "!python"
        tp.save()
        sp = self.add_project(
            "Libvirt-python",
            "libvir-list@redhat.com, libvirt-list@redhat.com",
            "https://github.com/libvirt/libvirt-python",
        )
        sp.prefix_tags = "python"
        sp.parent_project = tp
        sp.save()
        self.cli_import("0019-libvirt-python.mbox.gz")
        subj = "[libvirt] [python PATCH] event-test.py: Remove extra ( in --help output"
        self.check_cli(["search", "project:Libvirt"], stdout=subj)
        self.check_cli(["search", "project:Libvirt-python"], stdout=subj)
        sh = Message.objects.series_heads()
        self.assertEqual(len(sh), 1)
        s = sh[0]
        self.assertTrue(s.project.name, sp.name)

        self.cli_import("0020-libvirt.mbox.gz")
        # the order of the search results may change, so we cannot use stdout=...
        a, b = self.check_cli(["search", "project:Libvirt"])
        self.assertEqual(
            sorted(a.split("\n")),
            ["[libvirt]  [PATCH v2] vcpupin: add clear feature", subj],
        )
        self.check_cli(["search", "project:Libvirt-python"], stdout=subj)

    def test_import_no_to_header(self):
        self.add_project(
            "Linux",
            "linux-kernel@vger.kernel.org",
            "https://github.com/torvalds/linux",
        )
        self.cli_import("0036-patch-with-no-to-header.mbox.gz")
        a = "[PATCH] fpga: microsemi-spi: add Microsemi FPGA manager"
        self.check_cli(["search", "project:Linux"], stdout=a.strip())
        self.check_cli(["search", "project:QEMU"], stdout='')


class UnprivilegedImportTest(ImportTest):
    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.check_cli(
            ["project", "add", "QEMU", "--mailing-list", "qemu-devel@nongnu.org"]
        )
        self.cli_logout()
        self.create_user("importer", "importerpass", groups=["importers"])
        self.cli_login("importer", "importerpass")

    test_import_belong_to_multiple_projects = None

    def check_import_should_fail(self):
        self.cli_import("0001-simple-patch.mbox.gz", 1)
        a, b = self.check_cli(["search"])
        self.assertNotIn(
            "[Qemu-devel] [PATCH] quorum: Only compile when supported", a.splitlines()
        )

    def test_anonymous_import(self):
        self.cli_logout()
        self.check_import_should_fail()

    def test_normal_user_import(self):
        self.cli_logout()
        self.create_user("someuser", "somepass")
        self.cli_login("someuser", "somepass")
        self.check_import_should_fail()

    def test_project_update(self):
        p = Project.objects.all()[0]

        repo = self.create_git_repo()
        p.git = repo
        p.save()
        self.check_cli(["project", "update"])


if __name__ == "__main__":
    main()
