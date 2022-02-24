#!/usr/bin/env python3
#
# Copyright 2017 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import mbox

from .patchewtest import PatchewTestCase, main


class MboxTest(PatchewTestCase):
    def test_multipart_in_multipart(self):
        expected = """
On 07/25/2017 10:57 AM, Jeff Cody wrote:
> Signed-off-by: Jeff Cody <jcody@redhat.com>
> ---
>  redhat/build_configure.sh     | 3 +++
>  redhat/qemu-kvm.spec.template | 7 +++++++
>  2 files changed, 10 insertions(+)
>

ACK

--
Eric Blake, Principal Software Engineer
Red Hat, Inc.           +1-919-301-3266
Virtualization:  qemu.org | libvirt.org
        """.strip()
        dp = self.get_data_path("0016-nested-multipart.mbox.gz")
        with open(dp, "r") as f:
            msg = mbox.MboxMessage(f.read())
        self.assertEqual(msg.get_body().strip(), expected)

    def test_mime_word_recipient(self):
        dp = self.get_data_path("0018-mime-word-recipient.mbox.gz")
        with open(dp, "r") as f:
            msg = mbox.MboxMessage(f.read())
        utf8_recipient = msg.get_cc()[1]
        self.assertEqual(utf8_recipient[0], "Philippe Mathieu-Daudé")
        self.assertEqual(utf8_recipient[1], "f4bug@amsat.org")

    def test_mode_only_patch(self):
        dp = self.get_data_path("0021-mode-only-patch.mbox.gz")
        with open(dp, "r") as f:
            msg = mbox.MboxMessage(f.read())
        self.assertTrue(msg.is_patch())

    def test_rename_only_patch(self):
        dp = self.get_data_path("0034-rename-only-patch.mbox.gz")
        with open(dp, "r") as f:
            msg = mbox.MboxMessage(f.read())
        self.assertTrue(msg.is_patch())

    def test_raw_diff(self):
        dp = self.get_data_path("0033-raw-diff.mbox.gz")
        with open(dp, "r") as f:
            msg = mbox.MboxMessage(f.read())
        self.assertTrue(msg.is_patch())

    def test_rfc2047_from(self):
        dp = self.get_data_path("0035-rfc2047-from.mbox.gz")
        with open(dp, "r") as f:
            msg = mbox.MboxMessage(f.read())
        self.assertTrue(msg.get_from()[1] == "AIERPATIJIANG1@kingsoft.com")

    def test_get_json(self):
        dp = self.get_data_path("0001-simple-patch.mbox.gz")
        with open(dp, "r") as f:
            content = f.read()
            expected = {
                "message_id": "20160628014747.20971-1-famz@redhat.com",
                "in_reply_to": "",
                "date": "2016-06-28T01:47:47",
                "subject": "[Qemu-devel] [PATCH] quorum: Only compile when supported",
                "sender": {"name": "Fam Zheng", "address": "famz@redhat.com"},
                "recipients": [
                    {"address": "qemu-devel@nongnu.org"},
                    {"name": "Kevin Wolf", "address": "kwolf@redhat.com"},
                    {"name": "Alberto Garcia", "address": "berto@igalia.com"},
                    {"address": "qemu-block@nongnu.org"},
                    {"name": "Max Reitz", "address": "mreitz@redhat.com"},
                ],
                "mbox": content,
            }
            msg = mbox.MboxMessage(content).get_json()
        self.assertEqual(msg, expected)


if __name__ == "__main__":
    main()
