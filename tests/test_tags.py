#!/usr/bin/env python3
#
# Copyright 2017 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import email
import email.parser
import email.policy
from mbox import decode_payload

from .patchewtest import PatchewTestCase, main


class ImportTest(PatchewTestCase):
    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.p.prefix_tags = "!qemu-web"
        self.p.save()
        self.PROJECT_BASE = "%sprojects/%d/" % (self.REST_BASE, self.p.id)

    def test_import_one(self):
        resp = self.apply_and_retrieve(
            "0017-qemu-web-is-not-qemu.mbox.gz",
            self.p.id,
            "1504250391-6353-1-git-send-email-thuth@redhat.com",
        )
        self.assertEquals(resp.status_code, 404)

    def test_rest_single(self):
        resp = self.apply_and_retrieve(
            "0003-single-patch-reviewed.mbox.gz",
            self.p.id,
            "20160722095540.5887-1-paul.burton@imgtec.com",
        )
        uri = resp.data["message"]
        message = self.api_client.get(uri)
        self.assertEquals(
            message.data["tags"], ["Reviewed-by: Aurelien Jarno <aurelien@aurel32.net>"]
        )

    def test_rest_head(self):
        resp = self.apply_and_retrieve(
            "0004-multiple-patch-reviewed.mbox.gz",
            self.p.id,
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )
        uri = resp.data["message"]
        message = self.api_client.get(uri)
        self.assertEquals(
            message.data["tags"], ["Reviewed-by: Eric Blake <eblake@redhat.com>"]
        )
        for patch in resp.data["patches"]:
            uri = patch["resource_uri"]
            message = self.api_client.get(uri)
            self.assertEquals(message.data["tags"], [])
        for patch in resp.data["replies"]:
            uri = patch["resource_uri"]
            message = self.api_client.get(uri)
            self.assertEquals(message.data["tags"], [])

    def test_mbox_with_8bit_tags(self):
        self.cli_login()
        self.cli_import("0028-tags-need-8bit-encoding.mbox.gz")
        self.cli_logout()
        mbox = self.client.get("/QEMU/20181126152836.25379-1-rkagan@virtuozzo.com/mbox")
        parser = email.parser.BytesParser(policy=email.policy.SMTP)
        msg = parser.parsebytes(mbox.content)
        payload = decode_payload(msg)
        self.assertIn("SynICState *synic = get_synic(cs);", payload)
        self.assertIn(
            "Reviewed-by: Philippe Mathieu-Daudé <philmd@redhat.com>", payload
        )

    def test_case_insensitive(self):
        self.cli_login()
        self.cli_import("0002-unusual-cased-tags.mbox.gz")
        self.cli_logout()
        MESSAGE_ID = "20160628014747.20971-1-famz@redhat.com"
        resp = self.api_client.get(self.PROJECT_BASE + "messages/" + MESSAGE_ID + "/")
        self.assertEqual(
            {"name": "Fam Zheng", "address": "famz@redhat.com"},
            resp.data["reviewers"][0],
        )
        self.assertIn("Reviewed-By: Fam Zheng <famz@redhat.com>", resp.data["tags"])
        self.assertIn("tESTed-bY: Fam Zheng <famz@redhat.com>", resp.data["tags"])

    def test_obsoleted_by(self):
        self.cli_login()
        self.cli_import("0009-obsolete-by.mbox.gz")
        self.cli_logout()
        OLD_ID = "20160628014747.20971-1-famz@redhat.com"
        NEW_ID = "20160628014747.20971-2-famz@redhat.com"
        resp = self.api_client.get(self.PROJECT_BASE + "series/" + OLD_ID + "/")
        self.assertEqual(
            self.PROJECT_BASE + "series/" + NEW_ID + "/", resp.data["obsoleted_by"]
        )
        resp = self.api_client.get(self.PROJECT_BASE + "series/" + NEW_ID + "/")
        self.assertEqual(None, resp.data["obsoleted_by"])


if __name__ == "__main__":
    main()
