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

    def test_rest_single(self):
        resp = self.apply_and_retrieve('0003-single-patch-reviewed.mbox.gz',
                                       self.p.id, '20160722095540.5887-1-paul.burton@imgtec.com')
        uri = resp.data['message']
        message = self.api_client.get(uri)
        self.assertEquals(message.data['tags'], ['Reviewed-by: Aurelien Jarno <aurelien@aurel32.net>'])

    def test_rest_head(self):
        resp = self.apply_and_retrieve('0004-multiple-patch-reviewed.mbox.gz',
                                       self.p.id, '1469192015-16487-1-git-send-email-berrange@redhat.com')
        uri = resp.data['message']
        message = self.api_client.get(uri)
        self.assertEquals(message.data['tags'], ['Reviewed-by: Eric Blake <eblake@redhat.com>'])
        for patch in resp.data['patches']:
            uri = patch['resource_uri']
            message = self.api_client.get(uri)
            self.assertEquals(message.data['tags'], [])
        for patch in resp.data['replies']:
            uri = patch['resource_uri']
            message = self.api_client.get(uri)
            self.assertEquals(message.data['tags'], [])

if __name__ == '__main__':
    main()
