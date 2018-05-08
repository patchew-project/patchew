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

from django.contrib.auth.models import User

sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main
from api.models import Message
from api.rest import AddressSerializer
from collections import OrderedDict
import json

class RestTest(PatchewTestCase):
    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

        self.sp = self.add_project("QEMU Block Layer", "qemu-block@nongnu.org")
        self.sp.parent_project = self.p
        self.sp.prefix_tags = "block"
        self.sp.save()
        self.SUBPROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.sp.id)

        self.admin = User.objects.get(username='admin')
        self.USER_BASE = '%susers/%d/' % (self.REST_BASE, self.admin.id)

    def test_root(self):
        resp = self.api_client.get(self.REST_BASE)
        self.assertEquals(resp.data['users'], self.REST_BASE + 'users/')
        self.assertEquals(resp.data['projects'], self.REST_BASE + 'projects/')
        self.assertEquals(resp.data['series'], self.REST_BASE + 'series/')
        resp = self.api_client.get(self.REST_BASE, HTTP_HOST='patchew.org')
        self.assertEquals(resp.data['users'], 'http://patchew.org/api/v1/users/')
        self.assertEquals(resp.data['projects'], 'http://patchew.org/api/v1/projects/')
        self.assertEquals(resp.data['series'], 'http://patchew.org/api/v1/series/')

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
        self.assertEquals(resp.data['count'], 2)
        self.assertEquals(resp.data['results'][0]['resource_uri'], self.PROJECT_BASE)
        self.assertEquals(resp.data['results'][0]['name'], "QEMU")
        self.assertEquals(resp.data['results'][0]['mailing_list'], "qemu-devel@nongnu.org")
        self.assertEquals(resp.data['results'][1]['resource_uri'], self.SUBPROJECT_BASE)
        self.assertEquals(resp.data['results'][1]['name'], "QEMU Block Layer")
        self.assertEquals(resp.data['results'][1]['mailing_list'], "qemu-block@nongnu.org")
        self.assertEquals(resp.data['results'][1]['parent_project'], self.PROJECT_BASE)

    def test_project(self):
        resp = self.api_client.get(self.PROJECT_BASE)
        self.assertEquals(resp.data['resource_uri'], self.PROJECT_BASE)
        self.assertEquals(resp.data['name'], "QEMU")
        self.assertEquals(resp.data['mailing_list'], "qemu-devel@nongnu.org")
        resp = self.api_client.get(self.SUBPROJECT_BASE)
        self.assertEquals(resp.data['resource_uri'], self.SUBPROJECT_BASE)
        self.assertEquals(resp.data['name'], "QEMU Block Layer")
        self.assertEquals(resp.data['mailing_list'], "qemu-block@nongnu.org")
        self.assertEquals(resp.data['parent_project'], self.PROJECT_BASE)

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
            'parent_project': self.PROJECT_BASE,
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
        self.assertEquals(resp.data['parent_project'], self.PROJECT_BASE)

        resp = self.api_client.get(resp.data['resource_uri'])
        self.assertEquals(resp.data['name'], data['name'])
        self.assertEquals(resp.data['mailing_list'], data['mailing_list'])
        self.assertEquals(resp.data['prefix_tags'], data['prefix_tags'])
        self.assertEquals(resp.data['url'], data['url'])
        self.assertEquals(resp.data['git'], data['git'])
        self.assertEquals(resp.data['description'], data['description'])
        self.assertEquals(resp.data['display_order'], data['display_order'])
        self.assertEquals(resp.data['logo'], None)
        self.assertEquals(resp.data['parent_project'], self.PROJECT_BASE)

    def test_project_results_list(self):
        resp1 = self.api_client.get(self.PROJECT_BASE)
        resp = self.api_client.get(resp1.data['results'])
        self.assertEqual(resp.data['count'], len(resp.data['results']))

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
        self.assertEqual(resp.data['replies'][0]['resource_uri'], self.PROJECT_BASE + 'messages/5792265A.5070507@redhat.com/')
        self.assertEqual(resp.data['replies'][0]['in_reply_to'], '1469192015-16487-1-git-send-email-berrange@redhat.com')
        self.assertEqual(resp.data['replies'][0]['subject'], 'Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')
        self.assertEqual(resp.data['replies'][1]['resource_uri'], self.PROJECT_BASE + 'messages/e0858c00-ccb6-e533-ee3e-9ba84ca45a7b@redhat.com/')
        self.assertEqual(resp.data['replies'][1]['in_reply_to'], '1469192015-16487-1-git-send-email-berrange@redhat.com')
        self.assertEqual(resp.data['replies'][1]['subject'], 'Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')

        self.assertEqual(resp.data['patches'][0]['resource_uri'], self.PROJECT_BASE + 'messages/1469192015-16487-2-git-send-email-berrange@redhat.com/')
        self.assertEqual(resp.data['patches'][0]['subject'], '[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption')
        self.assertEqual(resp.data['patches'][0]['stripped_subject'], 'crypto: add support for querying parameters for block encryption')
        self.assertEqual(resp.data['patches'][1]['resource_uri'], self.PROJECT_BASE + 'messages/1469192015-16487-3-git-send-email-berrange@redhat.com/')
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

    def test_series_results_list(self):
        resp1 = self.apply_and_retrieve('0001-simple-patch.mbox.gz',
                                       self.p.id, '20160628014747.20971-1-famz@redhat.com')
        resp = self.api_client.get(resp1.data['results'])
        self.assertEqual(resp.data['count'], len(resp.data['results']))

    def test_series_search(self):
        resp1 = self.apply_and_retrieve('0004-multiple-patch-reviewed.mbox.gz',
                                        self.p.id, '1469192015-16487-1-git-send-email-berrange@redhat.com')
        resp2 = self.apply_and_retrieve('0001-simple-patch.mbox.gz',
                                        self.p.id, '20160628014747.20971-1-famz@redhat.com')

        resp = self.api_client.get(self.REST_BASE + 'series/?q=quorum')
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['resource_uri'], resp2.data['resource_uri'])
        self.assertEqual(resp.data['results'][0]['subject'], resp2.data['subject'])
        self.assertEqual('replies' in resp.data['results'][0], False)
        self.assertEqual('patches' in resp.data['results'][0], False)

        resp = self.api_client.get(self.REST_BASE + 'series/?q=project:QEMU')
        self.assertEqual(resp.data['count'], 2)
        self.assertEqual(resp.data['results'][0]['resource_uri'], resp1.data['resource_uri'])
        self.assertEqual(resp.data['results'][0]['subject'], resp1.data['subject'])
        self.assertEqual('replies' in resp.data['results'][0], False)
        self.assertEqual('patches' in resp.data['results'][0], False)
        self.assertEqual(resp.data['results'][1]['resource_uri'], resp2.data['resource_uri'])
        self.assertEqual(resp.data['results'][1]['subject'], resp2.data['subject'])
        self.assertEqual('replies' in resp.data['results'][1], False)
        self.assertEqual('patches' in resp.data['results'][1], False)

        resp = self.api_client.get(self.REST_BASE + 'projects/12345/series/?q=quorum')
        self.assertEqual(resp.data['count'], 0)
        resp = self.api_client.get(self.REST_BASE + 'projects/12345/series/?q=project:QEMU')
        self.assertEqual(resp.data['count'], 0)

    def test_series_delete(self):
        test_message_id = '1469192015-16487-1-git-send-email-berrange@redhat.com'
        series = self.apply_and_retrieve('0004-multiple-patch-reviewed.mbox.gz',self.p.id,
                                         test_message_id)
        message = series.data['message']
        resp_before = self.api_client.get(self.REST_BASE + 'projects/' + str(self.p.id)
                                          + '/series/' + test_message_id + '/')
        resp_reply_before = self.api_client.get(message + 'replies/')
        resp_without_login = self.api_client.delete(self.REST_BASE + 'projects/' + str(self.p.id)
                                      + '/series/' + test_message_id + '/')
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.delete(self.REST_BASE + 'projects/' + str(self.p.id)
                                      + '/series/' + test_message_id + '/')
        self.api_client.logout()
        resp_after = self.api_client.get(self.REST_BASE + 'projects/' + str(self.p.id)
                                         + '/series/' + test_message_id + '/')
        resp_reply_after = self.api_client.get(message + 'replies/')

        self.assertEqual(resp_before.status_code, 200)
        self.assertEqual(resp_reply_before.status_code, 200)
        self.assertEqual(resp_without_login.status_code, 403)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp_after.status_code, 404)
        self.assertEqual(resp_reply_after.status_code, 404)

    def test_create_message(self):
        data = {
                "message_id": "20171023201055.21973-11-andrew.smirnov@gmail.com",
                "subject": "[Qemu-devel] [PATCH v2 10/27] imx_fec: Reserve full 4K "
                           "page for the register file",
                "date": "2017-10-23T20:10:38",
                "sender": {
                    "name": "Andrey Smirnov",
                    "address": "andrew.smirnov@gmail.com"
                },
                "recipients": [
                    {
                    "address": "qemu-arm@nongnu.org"
                    },
                    {
                    "name": "Peter Maydell",
                    "address": "peter.maydell@linaro.org"
                    },
                    {
                    "name": "Andrey Smirnov",
                    "address": "andrew.smirnov@gmail.com"
                    },
                    {
                    "name": "Jason Wang",
                    "address": "jasowang@redhat.com"
                    },
                    {
                    "name": "Philippe Mathieu-Daudé",
                    "address": "f4bug@amsat.org"
                    },
                    {
                    "address": "qemu-devel@nongnu.org"
                    },
                    {
                    "address": "yurovsky@gmail.com"
                    }
                ],
                "mbox": "From andrew.smirnov@gmail.com Mon Oct 23 20:10:38 2017\nDelivered"
                        "-To: importer@patchew.org\nReceived-SPF: temperror (zoho.com: Err"
                        "or in retrieving data from DNS) client-ip=208.118.235.17; envelop"
                        "e-from=qemu-devel-bounces+importer=patchew.org@nongnu.org; helo=l"
                        "ists.gnu.org;\nAuthentication-Results: mx.zohomail.com;\n\tdkim=f"
                        "ail;\n\tspf=temperror (zoho.com: Error in retrieving data from DN"
                        "S)  smtp.mailfrom=qemu-devel-bounces+importer=patchew.org@nongnu."
                        "org\nReturn-Path: <qemu-devel-bounces+importer=patchew.org@nongnu"
                        ".org>\nReceived: from lists.gnu.org (208.118.235.17 [208.118.235."
                        "17]) by mx.zohomail.com\n\twith SMTPS id 1508790023478635.2925706"
                        "919272; Mon, 23 Oct 2017 13:20:23 -0700 (PDT)\nReceived: from loc"
                        "alhost ([::1]:40414 helo=lists.gnu.org)\n\tby lists.gnu.org with "
                        "esmtp (Exim 4.71)\n\t(envelope-from <qemu-devel-bounces+importer="
                        "patchew.org@nongnu.org>)\n\tid 1e6jCo-0007Cr-Ed\n\tfor importer@p"
                        "atchew.org; Mon, 23 Oct 2017 16:20:14 -0400\nReceived: from eggs."
                        "gnu.org ([2001:4830:134:3::10]:46254)\n\tby lists.gnu.org with es"
                        "mtp (Exim 4.71)\n\t(envelope-from <andrew.smirnov@gmail.com>) id "
                        "1e6j4M-0000Ia-AF\n\tfor qemu-devel@nongnu.org; Mon, 23 Oct 2017 1"
                        "6:11:32 -0400\nReceived: from Debian-exim by eggs.gnu.org with sp"
                        "am-scanned (Exim 4.71)\n\t(envelope-from <andrew.smirnov@gmail.co"
                        "m>) id 1e6j4L-0002WU-ES\n\tfor qemu-devel@nongnu.org; Mon, 23 Oct"
                        " 2017 16:11:30 -0400\nReceived: from mail-pf0-x241.google.com ([2"
                        "607:f8b0:400e:c00::241]:47361)\n\tby eggs.gnu.org with esmtps (TL"
                        "S1.0:RSA_AES_128_CBC_SHA1:16)\n\t(Exim 4.71) (envelope-from <andr"
                        "ew.smirnov@gmail.com>)\n\tid 1e6j4J-0002VQ-5h; Mon, 23 Oct 2017 1"
                        "6:11:27 -0400\nReceived: by mail-pf0-x241.google.com with SMTP id"
                        " z11so17896780pfk.4;\n\tMon, 23 Oct 2017 13:11:27 -0700 (PDT)\nRe"
                        "ceived: from squirtle.westlake.spaceflightindustries.com ([173.22"
                        "6.206.194])\n\tby smtp.gmail.com with ESMTPSA id\n\tj1sm15181623p"
                        "fj.108.2017.10.23.13.11.24\n\t(version=TLS1_2 cipher=ECDHE-RSA-CH"
                        "ACHA20-POLY1305 bits=256/256);\n\tMon, 23 Oct 2017 13:11:25 -0700"
                        " (PDT)\nDKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=g"
                        "mail.com; s=20161025;\n\th=from:to:cc:subject:date:message-id:in-"
                        "reply-to:references\n\t:mime-version:content-transfer-encoding;\n"
                        "\tbh=zmFol33kPLVHCkj7Ro+lVg1LTAQod/G9dNqJXtckibI=;\n\tb=D49+KCtse"
                        "bdshdA2kxqNqCWLEOTSRXI61CbfBrS3YYbGspt/3vTIRCLSKNhICr2UOc\n\t7BhL"
                        "XRtMKhn2gomHPqqSHOSp+hB5XtMmBNpBpkQyXMHoGkgmjg0IIF02Vzn4i2QzP8C9"
                        "\n\t0SDZb6VYnz70J5HY0KZwVfQ+Rc5qgJEfcTHzuzZ4qHcbXxPHYCGYo1yDG6bEU"
                        "LNp2sRB\n\tGekoCKine5V1Uc+8aKmIeQA3zTXj2BLYqIQFi3UdiEemj94Gs3UFkE"
                        "kV3kTtCBwBVYep\n\tCvtbjBMI4Kb2Rcyb7taNS1PwjoXo4nzyPqSftf5CtxE3FYQ"
                        "6pSHkU8H1cqi4os4RgACQ\n\t6rrA==\nX-Google-DKIM-Signature: v=1; a="
                        "rsa-sha256; c=relaxed/relaxed;\n\td=1e100.net; s=20161025;\n\th=x"
                        "-gm-message-state:from:to:cc:subject:date:message-id:in-reply-to"
                        "\n\t:references:mime-version:content-transfer-encoding;\n\tbh=zmF"
                        "ol33kPLVHCkj7Ro+lVg1LTAQod/G9dNqJXtckibI=;\n\tb=kG94Z4+JpBMpVNtWI"
                        "ASASHAaqcxeUgqF149vlfmPjsUsUZoE69zK/Xq8lz25p+TskP\n\tu+sFtsuT//gI"
                        "M/gFEeFYPBUEECFh+cSu6vYqjvy7W+o1dt0CkQS0K4sG2a6PDeXTc7Dw\n\tYOmEE"
                        "gzEW+JtEp27yE8L5Yiur7k9cMnq6AGsLtrNa4leHN8KfnBLpZDJ1w2BTVAST/Mt\n"
                        "\tp5OmcBALM2s2PfVxV2AqFIC03+BUkFo78Yl0dJkT95uUWQvXOrYnhrJGikBOpxf"
                        "e2GEl\n\tdX/N0knNvw1ILQigiiD7mTg2pWBXXdi9ncxWFbWGav3NFgMuMj9Le7dh"
                        "Merg+f0Pqzqq\n\tuMRw==\nX-Gm-Message-State: AMCzsaVtdnaUNbjj5huOS"
                        "I8ibhSVAiVnF57PiIS4oVle1IVoBcH6i/W4\n\tsAtvFi/nF5bYIYfQxgZMU93rvm"
                        "Mn\nX-Google-Smtp-Source: ABhQp+Tw1GtSPaSw51tZkI3AfiuyluStPI8C5/3"
                        "esBqFkirOMfsjtlRNoBcr8lgEf/55RwhQLiI5mQ==\nX-Received: by 10.98.6"
                        "5.218 with SMTP id g87mr14269292pfd.105.1508789486104;\n\tMon, 23"
                        " Oct 2017 13:11:26 -0700 (PDT)\nFrom: Andrey Smirnov <andrew.smir"
                        "nov@gmail.com>\nTo: qemu-arm@nongnu.org\nDate: Mon, 23 Oct 2017 1"
                        "3:10:38 -0700\nMessage-Id: <20171023201055.21973-11-andrew.smirno"
                        "v@gmail.com>\nX-Mailer: git-send-email 2.13.5\nIn-Reply-To: <2017"
                        "1023201055.21973-1-andrew.smirnov@gmail.com>\nReferences: <201710"
                        "23201055.21973-1-andrew.smirnov@gmail.com>\nMIME-Version: 1.0\nCo"
                        "ntent-Type: text/plain; charset=\"utf-8\"\nContent-Transfer-Encod"
                        "ing: base64\nX-detected-operating-system: by eggs.gnu.org: Genre "
                        "and OS details not\n\trecognized.\nX-Received-From: 2607:f8b0:400"
                        "e:c00::241\nSubject: [Qemu-devel] [PATCH v2 10/27] imx_fec: Reser"
                        "ve full 4K page for the\n register file\nX-BeenThere: qemu-devel@"
                        "nongnu.org\nX-Mailman-Version: 2.1.21\nPrecedence: list\nList-Id:"
                        " <qemu-devel.nongnu.org>\nList-Unsubscribe: <https://lists.nongnu"
                        ".org/mailman/options/qemu-devel>,\n\t<mailto:qemu-devel-request@n"
                        "ongnu.org?subject=unsubscribe>\nList-Archive: <http://lists.nongn"
                        "u.org/archive/html/qemu-devel/>\nList-Post: <mailto:qemu-devel@no"
                        "ngnu.org>\nList-Help: <mailto:qemu-devel-request@nongnu.org?subje"
                        "ct=help>\nList-Subscribe: <https://lists.nongnu.org/mailman/listi"
                        "nfo/qemu-devel>,\n\t<mailto:qemu-devel-request@nongnu.org?subject"
                        "=subscribe>\nCc: Peter Maydell <peter.maydell@linaro.org>,\n\tAnd"
                        "rey Smirnov <andrew.smirnov@gmail.com>,\n\tJason Wang <jasowang@r"
                        "edhat.com>,\n\t=?UTF-8?q?Philippe=20Mathieu-Daud=C3=A9?= <f4bug@a"
                        "msat.org>,\n\tqemu-devel@nongnu.org, yurovsky@gmail.com\nErrors-T"
                        "o: qemu-devel-bounces+importer=patchew.org@nongnu.org\nSender: \""
                        "Qemu-devel\" <qemu-devel-bounces+importer=patchew.org@nongnu.org>"
                        "\nX-ZohoMail-DKIM: fail (Header signature does not verify)\nX-Zoh"
                        "oMail: RDKM_2  RSF_6  Z_629925259 SPT_0\n\nU29tZSBpLk1YIFNvQ3MgKG"
                        "UuZy4gaS5NWDcpIGhhdmUgRkVDIHJlZ2lzdGVycyBnb2luZyBhcyBm\nYXIgYXMgb"
                        "2Zmc2V0CjB4NjE0LCBzbyB0byBhdm9pZCBnZXR0aW5nIGFib3J0cyB3aGVuIGFjY2"
                        "Vz\nc2luZyB0aG9zZSBvbiBRRU1VLCBleHRlbmQKdGhlIHJlZ2lzdGVyIGZpbGUgd"
                        "G8gY292ZXIgNEtC\nIG9mIGFkZHJlc3Mgc3BhY2UgaW5zdGVhZCBvZiBqdXN0IDFL"
                        "LgoKQ2M6IFBldGVyIE1heWRlbGwg\nPHBldGVyLm1heWRlbGxAbGluYXJvLm9yZz4"
                        "KQ2M6IEphc29uIFdhbmcgPGphc293YW5nQHJlZGhh\ndC5jb20+CkNjOiBQaGlsaX"
                        "BwZSBNYXRoaWV1LURhdWTDqSA8ZjRidWdAYW1zYXQub3JnPgpDYzog\ncWVtdS1kZ"
                        "XZlbEBub25nbnUub3JnCkNjOiBxZW11LWFybUBub25nbnUub3JnCkNjOiB5dXJvdn"
                        "Nr\neUBnbWFpbC5jb20KU2lnbmVkLW9mZi1ieTogQW5kcmV5IFNtaXJub3YgPGFuZ"
                        "HJldy5zbWlybm92\nQGdtYWlsLmNvbT4KLS0tCiBody9uZXQvaW14X2ZlYy5jIHwg"
                        "MiArLQogMSBmaWxlIGNoYW5nZWQs\nIDEgaW5zZXJ0aW9uKCspLCAxIGRlbGV0aW9"
                        "uKC0pCgpkaWZmIC0tZ2l0IGEvaHcvbmV0L2lteF9m\nZWMuYyBiL2h3L25ldC9pbX"
                        "hfZmVjLmMKaW5kZXggNDhkMDEyY2FkNi4uZTIzNmJjOTMzYyAxMDA2\nNDQKLS0tI"
                        "GEvaHcvbmV0L2lteF9mZWMuYworKysgYi9ody9uZXQvaW14X2ZlYy5jCkBAIC0xMj"
                        "Uy\nLDcgKzEyNTIsNyBAQCBzdGF0aWMgdm9pZCBpbXhfZXRoX3JlYWxpemUoRGV2a"
                        "WNlU3RhdGUgKmRl\ndiwgRXJyb3IgKiplcnJwKQogICAgIFN5c0J1c0RldmljZSAq"
                        "c2JkID0gU1lTX0JVU19ERVZJQ0Uo\nZGV2KTsKIAogICAgIG1lbW9yeV9yZWdpb25"
                        "faW5pdF9pbygmcy0+aW9tZW0sIE9CSkVDVChkZXYp\nLCAmaW14X2V0aF9vcHMsIH"
                        "MsCi0gICAgICAgICAgICAgICAgICAgICAgICAgIFRZUEVfSU1YX0ZF\nQywgMHg0M"
                        "DApOworICAgICAgICAgICAgICAgICAgICAgICAgICBUWVBFX0lNWF9GRUMsIDB4MT"
                        "Aw\nMCk7CiAgICAgc3lzYnVzX2luaXRfbW1pbyhzYmQsICZzLT5pb21lbSk7CiAgI"
                        "CAgc3lzYnVzX2lu\naXRfaXJxKHNiZCwgJnMtPmlycVswXSk7CiAgICAgc3lzYnVz"
                        "X2luaXRfaXJxKHNiZCwgJnMtPmly\ncVsxXSk7Ci0tIAoyLjEzLjUKCgo=\n\n"
                }
             
        resp = self.api_client.post(self.PROJECT_BASE + "messages/", json.dumps(data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        resp_get = self.api_client.get(self.PROJECT_BASE + "messages/20171023201055.21973-11-andrew.smirnov@gmail.com/")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp.data['subject'], "[Qemu-devel] [PATCH v2 10/27] imx_fec: Reserve full 4K "
                         "page for the register file")


    def test_message(self):
        series = self.apply_and_retrieve('0001-simple-patch.mbox.gz',
                                         self.p.id, '20160628014747.20971-1-famz@redhat.com')

        message = series.data['patches'][0]['resource_uri']
        resp = self.api_client.get(message)
        self.assertEqual(resp.data['mbox'], Message.objects.all()[0].get_mbox())

    def test_message_mbox(self):
        series = self.apply_and_retrieve('0001-simple-patch.mbox.gz',
                                         self.p.id, '20160628014747.20971-1-famz@redhat.com')

        message = series.data['patches'][0]['resource_uri']
        resp = self.client.get(message + 'mbox/')
        self.assertEqual(resp.data, Message.objects.all()[0].get_mbox())

    def test_address_serializer(self):
        data1 = {"name":"Shubham", "address":"shubhamjain7495@gmail.com"}
        serializer1 = AddressSerializer(data = data1)
        valid1 = serializer1.is_valid()
        valid_data1 = serializer1.validated_data
        data2 = {"name":123, "address":"shubhamjain7495@gmail.com"}
        serializer2 = AddressSerializer(data = data2)
        valid2 = serializer2.is_valid()
        valid_data2 = serializer2.validated_data

        self.assertEqual(valid1,True)
        self.assertEqual(valid_data1,OrderedDict([('name', 'Shubham'), ('address', 'shubhamjain7495@gmail.com')]))
        self.assertEqual(valid2,True)
        self.assertEqual(valid_data2,OrderedDict([('name', '123'), ('address', 'shubhamjain7495@gmail.com')]))

    def test_message_replies(self):
        series = self.apply_and_retrieve('0004-multiple-patch-reviewed.mbox.gz',
                                         self.p.id, '1469192015-16487-1-git-send-email-berrange@redhat.com')

        message = series.data['message']
        resp = self.api_client.get(message + 'replies/')
        self.assertEqual(resp.data['count'], 4)
        self.assertEqual(resp.data['results'][0]['resource_uri'], self.PROJECT_BASE + 'messages/1469192015-16487-2-git-send-email-berrange@redhat.com/')
        self.assertEqual(resp.data['results'][0]['subject'], '[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption')
        self.assertEqual(resp.data['results'][1]['resource_uri'], self.PROJECT_BASE + 'messages/1469192015-16487-3-git-send-email-berrange@redhat.com/')
        self.assertEqual(resp.data['results'][1]['subject'], '[Qemu-devel] [PATCH v4 2/2] block: export LUKS specific data to qemu-img info')
        self.assertEqual(resp.data['results'][2]['resource_uri'], self.PROJECT_BASE + 'messages/5792265A.5070507@redhat.com/')
        self.assertEqual(resp.data['results'][2]['subject'], 'Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')
        self.assertEqual(resp.data['results'][3]['resource_uri'], self.PROJECT_BASE + 'messages/e0858c00-ccb6-e533-ee3e-9ba84ca45a7b@redhat.com/')
        self.assertEqual(resp.data['results'][3]['subject'], 'Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver')

if __name__ == '__main__':
    main()
