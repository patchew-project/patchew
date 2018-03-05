#!/usr/bin/env python3
#
# Copyright 2017 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import os
import sys
import mbox
sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main

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

if __name__ == '__main__':
    main()
