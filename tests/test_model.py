#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from api.models import Message

from .patchewtest import PatchewTestCase, main


class ImportTest(PatchewTestCase):
    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.add_project("Patchew", "patchew-devel@redhat.com")

    def test_get_diff_stat(self):
        expected = """
hw/display/Kconfig                    | 5 +++++
hw/display/Makefile.objs              | 1 +
hw/{i2c => display}/i2c-ddc.c         | 2 +-
hw/display/sii9022.c                  | 2 +-
hw/display/sm501.c                    | 2 +-
hw/i2c/Kconfig                        | 5 -----
hw/i2c/Makefile.objs                  | 1 -
include/hw/{i2c => display}/i2c-ddc.h | 0
include/hw/display/xlnx_dp.h          | 2 +-
9 files changed, 10 insertions(+), 10 deletions(-)
rename hw/{i2c => display}/i2c-ddc.c (99%)
rename include/hw/{i2c => display}/i2c-ddc.h (100%)
"""
        self.cli_import("0008-complex-diffstat.mbox.gz")
        msg = Message.objects.first()
        self.maxDiff = 100000
        self.assertMultiLineEqual(expected.strip(), msg.get_diff_stat())

    def test_diff_stat_in_patch(self):
        expected = """
api/models.py                            |   4 +-
tests/data/0008-complex-diffstat.mbox.gz | Bin 4961 -> 2575 bytes
tests/test_model.py                      |  95 +++--------------------
3 files changed, 15 insertions(+), 84 deletions(-)
"""
        self.cli_import("0029-diffstat-in-patch.gz")
        msg = Message.objects.first()
        self.maxDiff = 100000
        self.assertMultiLineEqual(expected.strip(), msg.get_diff_stat())

    def test_mode_change_diff_stat(self):
        expected = """
tests/qemu-iotests/096 | 0
tests/qemu-iotests/129 | 0
tests/qemu-iotests/132 | 0
tests/qemu-iotests/136 | 0
tests/qemu-iotests/139 | 0
tests/qemu-iotests/148 | 0
tests/qemu-iotests/152 | 0
tests/qemu-iotests/163 | 0
tests/qemu-iotests/205 | 0
9 files changed, 0 insertions(+), 0 deletions(-)
mode change 100644 => 100755 tests/qemu-iotests/096
mode change 100644 => 100755 tests/qemu-iotests/129
mode change 100644 => 100755 tests/qemu-iotests/132
mode change 100644 => 100755 tests/qemu-iotests/136
mode change 100644 => 100755 tests/qemu-iotests/139
mode change 100644 => 100755 tests/qemu-iotests/148
mode change 100644 => 100755 tests/qemu-iotests/152
mode change 100644 => 100755 tests/qemu-iotests/163
mode change 100644 => 100755 tests/qemu-iotests/205
"""
        self.cli_import("0021-mode-only-patch.mbox.gz")
        msg = Message.objects.first()
        self.maxDiff = 100000
        self.assertMultiLineEqual(expected.strip(), msg.get_diff_stat())


if __name__ == "__main__":
    main()
