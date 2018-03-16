#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from patchewtest import PatchewTestCase, main
from api.models import Message

class ImportTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.add_project("QEMU", "qemu-devel@nongnu.org")

    def test_get_diff_stat(self):
        expected = """
MAINTAINERS                                        |   7 +
Makefile                                           |   9 +-
Makefile.objs                                      |   2 +
Makefile.target                                    |   2 +
block/qapi.c                                       |   4 +-
blockdev.c                                         |   4 +-
configure                                          |  36 ++
crypto/tlssession.c                                |  28 +-
docs/qapi-code-gen.txt                             |   4 +-
hmp.c                                              |  16 +-
include/qapi/qmp-input-visitor.h                   |  30 -
include/qapi/qmp/qdict.h                           |   1 +
include/qapi/qobject-input-visitor.h               |  85 +++
...p-output-visitor.h => qobject-output-visitor.h} |  10 +-
include/qemu/acl.h                                 |  66 ---
include/qemu/authz-pam.h                           |  98 ++++
include/qemu/authz-simple.h                        | 115 ++++
include/qemu/authz.h                               |  89 +++
include/qemu/option.h                              |   4 +
include/qom/object_interfaces.h                    |  10 +-
monitor.c                                          | 184 ++++--
qapi-schema.json                                   |   6 +-
qapi/Makefile.objs                                 |   4 +-
qapi/opts-visitor.c                                |  19 +-
qapi/qapi-clone-visitor.c                          |   2 +-
qapi/qmp-input-visitor.c                           | 412 --------------
qapi/qmp-output-visitor.c                          | 256 ---------
qapi/qobject-input-visitor.c                       | 624 +++++++++++++++++++++
qapi/qobject-output-visitor.c                      | 254 +++++++++
qapi/util.json                                     |  47 ++
qemu-img.c                                         |   8 +-
qmp.c                                              |   6 +-
qobject/qdict.c                                    | 283 ++++++++++
qom/object_interfaces.c                            |  47 +-
qom/qom-qobject.c                                  |   8 +-
scripts/qapi-commands.py                           |   8 +-
scripts/qapi-event.py                              |   4 +-
tests/.gitignore                                   |   7 +-
tests/Makefile.include                             |  25 +-
tests/check-qdict.c                                | 241 ++++++++
tests/check-qnull.c                                |   8 +-
tests/check-qom-proplist.c                         | 314 ++++++++++-
tests/test-authz-simple.c                          | 172 ++++++
tests/test-crypto-tlssession.c                     |  15 +-
tests/test-io-channel-tls.c                        |  16 +-
tests/test-qmp-commands.c                          |   4 +-
...-input-strict.c => test-qobject-input-strict.c} |   4 +-
...nput-visitor.c => test-qobject-input-visitor.c} | 154 ++++-
...put-visitor.c => test-qobject-output-visitor.c} |   4 +-
tests/test-string-input-visitor.c                  |   2 +-
tests/test-string-output-visitor.c                 |   2 +-
tests/test-visitor-serialization.c                 |   8 +-
ui/vnc-auth-sasl.c                                 |   2 +-
ui/vnc-auth-sasl.h                                 |   4 +-
ui/vnc.c                                           |  11 +-
util/Makefile.objs                                 |   7 +-
util/acl.c                                         | 179 ------
util/authz-pam.c                                   | 148 +++++
util/authz-simple.c                                | 314 +++++++++++
util/authz.c                                       |  47 ++
util/qemu-option.c                                 |  27 +-
util/qemu-sockets.c                                |   4 +-
62 files changed, 3354 insertions(+), 1157 deletions(-)
delete mode 100644 include/qapi/qmp-input-visitor.h
create mode 100644 include/qapi/qobject-input-visitor.h
rename include/qapi/{qmp-output-visitor.h => qobject-output-visitor.h} (66%)
delete mode 100644 include/qemu/acl.h
create mode 100644 include/qemu/authz-pam.h
create mode 100644 include/qemu/authz-simple.h
create mode 100644 include/qemu/authz.h
delete mode 100644 qapi/qmp-input-visitor.c
delete mode 100644 qapi/qmp-output-visitor.c
create mode 100644 qapi/qobject-input-visitor.c
create mode 100644 qapi/qobject-output-visitor.c
create mode 100644 qapi/util.json
create mode 100644 tests/test-authz-simple.c
rename tests/{test-qmp-input-strict.c => test-qobject-input-strict.c} (99%)
rename tests/{test-qmp-input-visitor.c => test-qobject-input-visitor.c} (86%)
rename tests/{test-qmp-output-visitor.c => test-qobject-output-visitor.c} (99%)
delete mode 100644 util/acl.c
create mode 100644 util/authz-pam.c
create mode 100644 util/authz-simple.c
create mode 100644 util/authz.c
"""
        self.cli_import("0008-complex-diffstat.mbox.gz")
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

if __name__ == '__main__':
    main()
