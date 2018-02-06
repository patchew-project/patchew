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
import json
import tempfile
import shutil
import subprocess

from django.contrib.auth.models import User, Group

sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main
from api.models import Message

class RestTest(PatchewTestCase):
    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

        self.admin = User.objects.get(username='admin')
        self.USER_BASE = '%susers/%d/' % (self.REST_BASE, self.admin.id)

    def test_users(self):
        resp = self.api_client.get(self.REST_BASE + 'users/')
        self.assertEquals(resp.data['count'], 1)
        self.assertEquals(resp.data['results'][0]['resource_uri'], self.USER_BASE)
        self.assertEquals(resp.data['results'][0]['username'], self.admin.username)

    def test_user(self):
        resp = self.api_client.get(self.USER_BASE)
        self.assertEquals(resp.data['resource_uri'], self.USER_BASE)
        self.assertEquals(resp.data['username'], self.admin.username)

    def test_projects(self):
        resp = self.api_client.get(self.REST_BASE + 'projects/')
        self.assertEquals(resp.data['count'], 1)
        self.assertEquals(resp.data['results'][0]['resource_uri'], self.PROJECT_BASE)
        self.assertEquals(resp.data['results'][0]['name'], "QEMU")
        self.assertEquals(resp.data['results'][0]['mailing_list'], "qemu-devel@nongnu.org")

    def test_project(self):
        resp = self.api_client.get(self.PROJECT_BASE)
        self.assertEquals(resp.data['resource_uri'], self.PROJECT_BASE)
        self.assertEquals(resp.data['name'], "QEMU")
        self.assertEquals(resp.data['mailing_list'], "qemu-devel@nongnu.org")

    def test_project_post_minimal(self):
        data = {
            'name': 'keycodemapdb',
        }
        resp = self.api_client.post(self.REST_BASE + 'projects/', data=data)
        self.assertEquals(resp.status_code, 201)
        self.assertEquals(resp.data['resource_uri'].startswith(self.REST_BASE + 'projects/'), True)
        self.assertEquals(resp.data['name'], data['name'])

        resp = self.api_client.get(resp.data['resource_uri'])
        self.assertEquals(resp.data['name'], data['name'])

    def test_project_post(self):
        data = {
            'name': 'keycodemapdb',
            'mailing_list': 'qemu-devel@nongnu.org',
            'prefix_tags': 'keycodemapdb',
            'url': 'https://gitlab.com/keycodemap/keycodemapdb/',
            'git': 'https://gitlab.com/keycodemap/keycodemapdb/',
            'description': 'keycodemapdb generates code to translate key codes',
            'display_order': 4321,
        }
        resp = self.api_client.post(self.REST_BASE + 'projects/', data=data)
        self.assertEquals(resp.status_code, 201)
        self.assertEquals(resp.data['resource_uri'].startswith(self.REST_BASE + 'projects/'), True)
        self.assertEquals(resp.data['name'], data['name'])
        self.assertEquals(resp.data['mailing_list'], data['mailing_list'])
        self.assertEquals(resp.data['prefix_tags'], data['prefix_tags'])
        self.assertEquals(resp.data['url'], data['url'])
        self.assertEquals(resp.data['git'], data['git'])
        self.assertEquals(resp.data['description'], data['description'])
        self.assertEquals(resp.data['display_order'], data['display_order'])
        self.assertEquals(resp.data['logo'], None)

        resp = self.api_client.get(resp.data['resource_uri'])
        self.assertEquals(resp.data['name'], data['name'])
        self.assertEquals(resp.data['mailing_list'], data['mailing_list'])
        self.assertEquals(resp.data['prefix_tags'], data['prefix_tags'])
        self.assertEquals(resp.data['url'], data['url'])
        self.assertEquals(resp.data['git'], data['git'])
        self.assertEquals(resp.data['description'], data['description'])
        self.assertEquals(resp.data['display_order'], data['display_order'])
        self.assertEquals(resp.data['logo'], None)

    def test_series_single(self):
        resp = self.apply_and_retrieve('0001-simple-patch.mbox.gz',
                                       self.p.id, '20160628014747.20971-1-famz@redhat.com')

        self.assertEqual(resp.data['subject'], '[Qemu-devel] [PATCH] quorum: Only compile when supported')
        self.assertEqual(resp.data['stripped_subject'], 'quorum: Only compile when supported')
        self.assertEqual(resp.data['is_complete'], True)
        self.assertEqual(resp.data['total_patches'], 1)
        self.assertEqual(len(resp.data['replies']), 0)
        self.assertEqual(len(resp.data['patches']), 1)

        self.assertEqual(resp.data['patches'][0]['subject'], resp.data['subject'])
        self.assertEqual(resp.data['patches'][0]['stripped_subject'], resp.data['stripped_subject'])

    def test_series_multiple(self):
        resp = self.apply_and_retrieve('0004-multiple-patch-reviewed.mbox.gz',
                                       self.p.id, '1469192015-16487-1-git-send-email-berrange@redhat.com')

        self.assertEqual(resp.data['subject'], '[Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')
        self.assertEqual(resp.data['stripped_subject'], 'Report format specific info for LUKS block driver')
        self.assertEqual(resp.data['is_complete'], True)
        self.assertEqual(resp.data['total_patches'], 2)
        self.assertEqual(len(resp.data['replies']), 2)
        self.assertEqual(len(resp.data['patches']), 2)
        self.assertEqual(resp.data['replies'][0]['in_reply_to'], '1469192015-16487-1-git-send-email-berrange@redhat.com')
        self.assertEqual(resp.data['replies'][0]['subject'], 'Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')
        self.assertEqual(resp.data['replies'][1]['in_reply_to'], '1469192015-16487-1-git-send-email-berrange@redhat.com')
        self.assertEqual(resp.data['replies'][1]['subject'], 'Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')

        self.assertEqual(resp.data['patches'][0]['subject'], '[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption')
        self.assertEqual(resp.data['patches'][0]['stripped_subject'], 'crypto: add support for querying parameters for block encryption')
        self.assertEqual(resp.data['patches'][1]['subject'], '[Qemu-devel] [PATCH v4 2/2] block: export LUKS specific data to qemu-img info')
        self.assertEqual(resp.data['patches'][1]['stripped_subject'], 'block: export LUKS specific data to qemu-img info')

    def test_series_incomplete(self):
        resp = self.apply_and_retrieve('0012-incomplete-series.mbox.gz',
                                       self.p.id, '1469192015-16487-1-git-send-email-berrange@redhat.com')

        self.assertEqual(resp.data['subject'], '[Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')
        self.assertEqual(resp.data['stripped_subject'], 'Report format specific info for LUKS block driver')
        self.assertEqual(resp.data['is_complete'], False)
        self.assertEqual(resp.data['total_patches'], 2)
        self.assertEqual(len(resp.data['replies']), 2)
        self.assertEqual(len(resp.data['patches']), 1)

        self.assertEqual(resp.data['patches'][0]['subject'], '[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption')
        self.assertEqual(resp.data['patches'][0]['stripped_subject'], 'crypto: add support for querying parameters for block encryption')

    def test_series_list(self):
        resp1 = self.apply_and_retrieve('0004-multiple-patch-reviewed.mbox.gz',
                                        self.p.id, '1469192015-16487-1-git-send-email-berrange@redhat.com')
        resp2 = self.apply_and_retrieve('0001-simple-patch.mbox.gz',
                                        self.p.id, '20160628014747.20971-1-famz@redhat.com')

        resp = self.api_client.get(self.REST_BASE + 'series/')
        self.assertEqual(resp.data['count'], 2)

        resp = self.api_client.get(self.PROJECT_BASE + 'series/')
        self.assertEqual(resp.data['count'], 2)

        resp = self.api_client.get(self.REST_BASE + 'projects/12345/series/')
        self.assertEqual(resp.data['count'], 0)

if __name__ == '__main__':
    main()
