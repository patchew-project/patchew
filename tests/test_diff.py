#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import sys
import os
sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main

class DiffTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

    def test_rest_version(self):
        resp = self.apply_and_retrieve('0004-multiple-patch-reviewed.mbox.gz',
                                       self.p.id, '1469192015-16487-1-git-send-email-berrange@redhat.com')
        self.assertEqual(resp.data['version'], 4)

        resp = self.apply_and_retrieve('0001-simple-patch.mbox.gz',
                                       self.p.id, '20160628014747.20971-1-famz@redhat.com')
        self.assertEqual(resp.data['version'], 1)

    def test_rest_other_versions_only_in_detail(self):
        self.cli_login()
        self.cli_import("0009-obsolete-by.mbox.gz")

        resp = self.api_client.get(self.REST_BASE + 'series/?q=quorum')
        self.assertEqual(resp.data['count'], 3)
        results = sorted(resp.data['results'], key=lambda y: y['version'])
        self.assertEqual(results[0]['version'], 1)
        self.assertEqual(results[1]['version'], 2)
        self.assertEqual(results[2]['version'], 3)
        self.assertEqual('other_versions' in resp.data['results'][0], False)
        self.assertEqual('other_versions' in resp.data['results'][1], False)
        self.assertEqual('other_versions' in resp.data['results'][2], False)

    def test_rest_other_versions(self):
        self.cli_login()
        self.cli_import("0009-obsolete-by.mbox.gz")

        resp1 = self.api_client.get(self.PROJECT_BASE + 'series/20160628014747.20971-1-famz@redhat.com/')
        resp2 = self.api_client.get(self.PROJECT_BASE + 'series/20160628014747.20971-2-famz@redhat.com/')
        resp3 = self.api_client.get(self.PROJECT_BASE + 'series/20160628014747.20971-3-famz@redhat.com/')
        self.assertEqual(resp1.data['other_versions'][0]['version'], 2)
        self.assertEqual(resp1.data['other_versions'][0]['resource_uri'], resp2.data['resource_uri'])
        self.assertEqual(resp1.data['other_versions'][1]['version'], 3)
        self.assertEqual(resp1.data['other_versions'][1]['resource_uri'], resp3.data['resource_uri'])
        self.assertEqual(resp2.data['other_versions'][0]['version'], 1)
        self.assertEqual(resp2.data['other_versions'][0]['resource_uri'], resp1.data['resource_uri'])
        self.assertEqual(resp2.data['other_versions'][1]['version'], 3)
        self.assertEqual(resp2.data['other_versions'][1]['resource_uri'], resp3.data['resource_uri'])
        self.assertEqual(resp3.data['other_versions'][0]['version'], 1)
        self.assertEqual(resp3.data['other_versions'][0]['resource_uri'], resp1.data['resource_uri'])
        self.assertEqual(resp3.data['other_versions'][1]['version'], 2)
        self.assertEqual(resp3.data['other_versions'][1]['resource_uri'], resp2.data['resource_uri'])

if __name__ == '__main__':
    main()
