#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from collections import OrderedDict
import json

from django.contrib.auth.models import User

from api.models import Message
from api.rest import AddressSerializer

from .patchewtest import PatchewTestCase, main

try:
    import coreapi
except ImportError:
    coreapi = None


class RestTest(PatchewTestCase):
    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.PROJECT_BASE = "%sprojects/%d/" % (self.REST_BASE, self.p.id)

        self.sp = self.add_project("QEMU Block Layer", "qemu-block@nongnu.org")
        self.sp.parent_project = self.p
        self.sp.prefix_tags = "block"
        self.sp.save()
        self.SUBPROJECT_BASE = "%sprojects/%d/" % (self.REST_BASE, self.sp.id)
        self.p2 = self.add_project("EDK 2", "edk2-devel@lists.01.org")
        self.PROJECT_BASE_2 = "%sprojects/%d/" % (self.REST_BASE, self.p2.id)

        self.admin = User.objects.get(username="admin")
        self.USER_BASE = "%susers/%d/" % (self.REST_BASE, self.admin.id)

    def test_root(self):
        resp = self.api_client.get(self.REST_BASE)
        self.assertEquals(resp.data["users"], self.REST_BASE + "users/")
        self.assertEquals(resp.data["projects"], self.REST_BASE + "projects/")
        self.assertEquals(resp.data["series"], self.REST_BASE + "series/")
        resp = self.api_client.get(self.REST_BASE, HTTP_HOST="patchew.org")
        self.assertEquals(resp.data["users"], "http://patchew.org/api/v1/users/")
        self.assertEquals(resp.data["projects"], "http://patchew.org/api/v1/projects/")
        self.assertEquals(resp.data["series"], "http://patchew.org/api/v1/series/")

    def test_users(self):
        resp = self.api_client.get(self.REST_BASE + "users/")
        self.assertEquals(resp.data["count"], 1)
        self.assertEquals(resp.data["results"][0]["resource_uri"], self.USER_BASE)
        self.assertEquals(resp.data["results"][0]["username"], self.admin.username)

    def test_user(self):
        resp = self.api_client.get(self.USER_BASE)
        self.assertEquals(resp.data["resource_uri"], self.USER_BASE)
        self.assertEquals(resp.data["username"], self.admin.username)

    def test_projects(self):
        resp = self.api_client.get(self.REST_BASE + "projects/")
        self.assertEquals(resp.data["count"], 3)
        self.assertEquals(resp.data["results"][0]["resource_uri"], self.PROJECT_BASE)
        self.assertEquals(resp.data["results"][0]["name"], "QEMU")
        self.assertEquals(
            resp.data["results"][0]["mailing_list"], "qemu-devel@nongnu.org"
        )
        self.assertEquals(resp.data["results"][1]["resource_uri"], self.SUBPROJECT_BASE)
        self.assertEquals(resp.data["results"][1]["name"], "QEMU Block Layer")
        self.assertEquals(
            resp.data["results"][1]["mailing_list"], "qemu-block@nongnu.org"
        )
        self.assertEquals(resp.data["results"][1]["parent_project"], self.PROJECT_BASE)

    def test_project(self):
        resp = self.api_client.get(self.PROJECT_BASE)
        self.assertEquals(resp.data["resource_uri"], self.PROJECT_BASE)
        self.assertEquals(resp.data["name"], "QEMU")
        self.assertEquals(resp.data["mailing_list"], "qemu-devel@nongnu.org")
        resp = self.api_client.get(self.SUBPROJECT_BASE)
        self.assertEquals(resp.data["resource_uri"], self.SUBPROJECT_BASE)
        self.assertEquals(resp.data["name"], "QEMU Block Layer")
        self.assertEquals(resp.data["mailing_list"], "qemu-block@nongnu.org")
        self.assertEquals(resp.data["parent_project"], self.PROJECT_BASE)

    def test_project_by_name(self):
        resp = self.api_client.get(self.REST_BASE + "projects/by-name/QEMU/")
        self.assertEquals(resp.status_code, 307)
        resp = self.api_client.get(resp["Location"])
        self.assertEquals(resp.data["resource_uri"], self.PROJECT_BASE)
        self.assertEquals(resp.data["name"], "QEMU")
        self.assertEquals(resp.data["mailing_list"], "qemu-devel@nongnu.org")
        resp = self.api_client.get(
            self.REST_BASE + "projects/by-name/QEMU/?some=thing&foo=bar"
        )
        self.assertEquals(resp.status_code, 307)
        self.assertIn("some=thing", resp["Location"])
        self.assertIn("foo=bar", resp["Location"])

    def test_project_config_get(self):
        self.p.config = {"git": {"push_to": "/tmp/aaa"}}
        self.p.save()
        resp = self.api_client.get(self.PROJECT_BASE + "config/")
        self.assertEquals(resp.status_code, 401)
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.get(self.PROJECT_BASE + "config/")
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.data["git"]["push_to"], "/tmp/aaa")

    def test_project_config_put(self):
        new_config = {"git": {"push_to": "/tmp/bbb"}}
        resp = self.api_client.put(
            self.PROJECT_BASE + "config/", new_config, format="json"
        )
        self.assertEquals(resp.status_code, 401)
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.put(
            self.PROJECT_BASE + "config/", new_config, format="json"
        )
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.data["git"]["push_to"], "/tmp/bbb")
        resp = self.api_client.get(self.PROJECT_BASE + "config/")
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.data["git"]["push_to"], "/tmp/bbb")

    def test_update_project_head(self):
        resp = self.apply_and_retrieve(
            "0001-simple-patch.mbox.gz",
            self.p.id,
            "20160628014747.20971-1-famz@redhat.com",
        )
        self.api_client.login(username=self.user, password=self.password)
        resp_before = self.api_client.get(
            self.PROJECT_BASE + "series/" + "20160628014747.20971-1-famz@redhat.com/"
        )
        data = {
            "message_ids": ["20160628014747.20971-1-famz@redhat.com"],
            "old_head": "None",
            "new_head": "000000",
        }
        resp = self.api_client.post(
            self.PROJECT_BASE + "update_project_head/",
            data=json.dumps(data),
            content_type="application/json",
        )
        resp_after = self.api_client.get(
            self.PROJECT_BASE + "series/" + "20160628014747.20971-1-famz@redhat.com/"
        )
        self.assertEquals(resp_before.data["is_merged"], False)
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp.data["count"], 1)
        self.assertEquals(resp.data["new_head"], "000000")
        self.assertEquals(resp_after.data["is_merged"], True)

    def test_project_post_no_login(self):
        data = {"name": "keycodemapdb"}
        resp = self.api_client.post(self.REST_BASE + "projects/", data=data)
        self.assertEquals(resp.status_code, 401)

    def test_project_post_minimal(self):
        data = {"name": "keycodemapdb"}
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.post(self.REST_BASE + "projects/", data=data)
        self.assertEquals(resp.status_code, 201)
        self.assertEquals(
            resp.data["resource_uri"].startswith(self.REST_BASE + "projects/"), True
        )
        self.assertEquals(resp.data["name"], data["name"])

        resp = self.api_client.get(resp.data["resource_uri"])
        self.assertEquals(resp.data["name"], data["name"])

    def test_project_post(self):
        self.api_client.login(username=self.user, password=self.password)
        data = {
            "name": "keycodemapdb",
            "mailing_list": "qemu-devel@nongnu.org",
            "prefix_tags": "keycodemapdb",
            "url": "https://gitlab.com/keycodemap/keycodemapdb/",
            "git": "https://gitlab.com/keycodemap/keycodemapdb/",
            "description": "keycodemapdb generates code to translate key codes",
            "display_order": 4321,
            "parent_project": self.PROJECT_BASE,
        }
        resp = self.api_client.post(self.REST_BASE + "projects/", data=data)
        self.assertEquals(resp.status_code, 201)
        self.assertEquals(
            resp.data["resource_uri"].startswith(self.REST_BASE + "projects/"), True
        )
        self.assertEquals(resp.data["name"], data["name"])
        self.assertEquals(resp.data["mailing_list"], data["mailing_list"])
        self.assertEquals(resp.data["prefix_tags"], data["prefix_tags"])
        self.assertEquals(resp.data["url"], data["url"])
        self.assertEquals(resp.data["git"], data["git"])
        self.assertEquals(resp.data["description"], data["description"])
        self.assertEquals(resp.data["display_order"], data["display_order"])
        self.assertEquals(resp.data["logo"], None)
        self.assertEquals(resp.data["parent_project"], self.PROJECT_BASE)

        resp = self.api_client.get(resp.data["resource_uri"])
        self.assertEquals(resp.data["name"], data["name"])
        self.assertEquals(resp.data["mailing_list"], data["mailing_list"])
        self.assertEquals(resp.data["prefix_tags"], data["prefix_tags"])
        self.assertEquals(resp.data["url"], data["url"])
        self.assertEquals(resp.data["git"], data["git"])
        self.assertEquals(resp.data["description"], data["description"])
        self.assertEquals(resp.data["display_order"], data["display_order"])
        self.assertEquals(resp.data["logo"], None)
        self.assertEquals(resp.data["parent_project"], self.PROJECT_BASE)

    def test_project_results_list(self):
        resp1 = self.api_client.get(self.PROJECT_BASE)
        resp = self.api_client.get(resp1.data["results"])
        self.assertEqual(resp.data["count"], len(resp.data["results"]))

    def test_series_single(self):
        resp = self.apply_and_retrieve(
            "0001-simple-patch.mbox.gz",
            self.p.id,
            "20160628014747.20971-1-famz@redhat.com",
        )

        self.assertEqual(
            resp.data["subject"],
            "[Qemu-devel] [PATCH] quorum: Only compile when supported",
        )
        self.assertEqual(
            resp.data["stripped_subject"], "quorum: Only compile when supported"
        )
        self.assertEqual(resp.data["is_complete"], True)
        self.assertEqual(resp.data["total_patches"], 1)
        self.assertEqual(len(resp.data["replies"]), 0)
        self.assertEqual(len(resp.data["patches"]), 1)

        self.assertEqual(resp.data["patches"][0]["subject"], resp.data["subject"])
        self.assertEqual(
            resp.data["patches"][0]["stripped_subject"], resp.data["stripped_subject"]
        )

    def test_series_multiple(self):
        resp = self.apply_and_retrieve(
            "0004-multiple-patch-reviewed.mbox.gz",
            self.p.id,
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )

        self.assertEqual(
            resp.data["subject"],
            "[Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver",
        )
        self.assertEqual(
            resp.data["stripped_subject"],
            "Report format specific info for LUKS block driver",
        )
        self.assertEqual(resp.data["is_complete"], True)
        self.assertEqual(resp.data["total_patches"], 2)
        self.assertEqual(len(resp.data["replies"]), 2)
        self.assertEqual(len(resp.data["patches"]), 2)
        self.assertEqual(
            resp.data["replies"][0]["resource_uri"],
            self.PROJECT_BASE + "messages/5792265A.5070507@redhat.com/",
        )
        self.assertEqual(
            resp.data["replies"][0]["in_reply_to"],
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )
        self.assertEqual(
            resp.data["replies"][0]["subject"],
            "Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver",
        )
        self.assertEqual(
            resp.data["replies"][1]["resource_uri"],
            self.PROJECT_BASE
            + "messages/e0858c00-ccb6-e533-ee3e-9ba84ca45a7b@redhat.com/",
        )
        self.assertEqual(
            resp.data["replies"][1]["in_reply_to"],
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )
        self.assertEqual(
            resp.data["replies"][1]["subject"],
            "Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver",
        )

        self.assertEqual(
            resp.data["patches"][0]["resource_uri"],
            self.PROJECT_BASE
            + "messages/1469192015-16487-2-git-send-email-berrange@redhat.com/",
        )
        self.assertEqual(
            resp.data["patches"][0]["subject"],
            "[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption",
        )
        self.assertEqual(
            resp.data["patches"][0]["stripped_subject"],
            "crypto: add support for querying parameters for block encryption",
        )
        self.assertEqual(
            resp.data["patches"][1]["resource_uri"],
            self.PROJECT_BASE
            + "messages/1469192015-16487-3-git-send-email-berrange@redhat.com/",
        )
        self.assertEqual(
            resp.data["patches"][1]["subject"],
            "[Qemu-devel] [PATCH v4 2/2] block: export LUKS specific data to qemu-img info",
        )
        self.assertEqual(
            resp.data["patches"][1]["stripped_subject"],
            "block: export LUKS specific data to qemu-img info",
        )

    def test_series_incomplete(self):
        resp = self.apply_and_retrieve(
            "0012-incomplete-series.mbox.gz",
            self.p.id,
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )

        self.assertEqual(
            resp.data["subject"],
            "[Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver",
        )
        self.assertEqual(
            resp.data["stripped_subject"],
            "Report format specific info for LUKS block driver",
        )
        self.assertEqual(resp.data["is_complete"], False)
        self.assertEqual(resp.data["total_patches"], 2)
        self.assertEqual(len(resp.data["replies"]), 2)
        self.assertEqual(len(resp.data["patches"]), 1)

        self.assertEqual(
            resp.data["patches"][0]["subject"],
            "[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption",
        )
        self.assertEqual(
            resp.data["patches"][0]["stripped_subject"],
            "crypto: add support for querying parameters for block encryption",
        )

    def test_series_list(self):
        self.apply_and_retrieve(
            "0004-multiple-patch-reviewed.mbox.gz",
            self.p.id,
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )
        self.apply_and_retrieve(
            "0001-simple-patch.mbox.gz",
            self.p.id,
            "20160628014747.20971-1-famz@redhat.com",
        )

        resp = self.api_client.get(self.REST_BASE + "series/")
        self.assertEqual(resp.data["count"], 2)

        resp = self.api_client.get(self.PROJECT_BASE + "series/")
        self.assertEqual(resp.data["count"], 2)

        resp = self.api_client.get(self.REST_BASE + "projects/12345/series/")
        self.assertEqual(resp.status_code, 404)

    def test_series_results_list(self):
        resp1 = self.apply_and_retrieve(
            "0001-simple-patch.mbox.gz",
            self.p.id,
            "20160628014747.20971-1-famz@redhat.com",
        )
        resp = self.api_client.get(resp1.data["results"])
        self.assertEqual(resp.data["count"], len(resp.data["results"]))

    def test_series_search(self):
        resp1 = self.apply_and_retrieve(
            "0004-multiple-patch-reviewed.mbox.gz",
            self.p.id,
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )
        resp2 = self.apply_and_retrieve(
            "0001-simple-patch.mbox.gz",
            self.p.id,
            "20160628014747.20971-1-famz@redhat.com",
        )

        resp = self.api_client.get(self.REST_BASE + "series/?q=quorum")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(
            resp.data["results"][0]["resource_uri"], resp2.data["resource_uri"]
        )
        self.assertEqual(resp.data["results"][0]["subject"], resp2.data["subject"])
        self.assertEqual("replies" in resp.data["results"][0], False)
        self.assertEqual("patches" in resp.data["results"][0], False)

        resp = self.api_client.get(self.REST_BASE + "series/?q=project:QEMU")
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(
            resp.data["results"][0]["resource_uri"], resp1.data["resource_uri"]
        )
        self.assertEqual(resp.data["results"][0]["subject"], resp1.data["subject"])
        self.assertEqual("replies" in resp.data["results"][0], False)
        self.assertEqual("patches" in resp.data["results"][0], False)
        self.assertEqual(
            resp.data["results"][1]["resource_uri"], resp2.data["resource_uri"]
        )
        self.assertEqual(resp.data["results"][1]["subject"], resp2.data["subject"])
        self.assertEqual("replies" in resp.data["results"][1], False)
        self.assertEqual("patches" in resp.data["results"][1], False)

        resp = self.api_client.get(self.REST_BASE + "projects/12345/series/?q=quorum")
        self.assertEqual(resp.status_code, 404)
        resp = self.api_client.get(
            self.REST_BASE + "projects/12345/series/?q=project:QEMU"
        )
        self.assertEqual(resp.status_code, 404)

    def test_series_delete(self):
        test_message_id = "1469192015-16487-1-git-send-email-berrange@redhat.com"
        series = self.apply_and_retrieve(
            "0004-multiple-patch-reviewed.mbox.gz", self.p.id, test_message_id
        )
        message = series.data["message"]
        resp_before = self.api_client.get(
            self.REST_BASE
            + "projects/"
            + str(self.p.id)
            + "/series/"
            + test_message_id
            + "/"
        )
        resp_reply_before = self.api_client.get(message + "replies/")
        resp_without_login = self.api_client.delete(
            self.REST_BASE
            + "projects/"
            + str(self.p.id)
            + "/series/"
            + test_message_id
            + "/"
        )
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.delete(
            self.REST_BASE
            + "projects/"
            + str(self.p.id)
            + "/series/"
            + test_message_id
            + "/"
        )
        self.api_client.logout()
        resp_after = self.api_client.get(
            self.REST_BASE
            + "projects/"
            + str(self.p.id)
            + "/series/"
            + test_message_id
            + "/"
        )
        resp_reply_after = self.api_client.get(message + "replies/")

        self.assertEqual(resp_before.status_code, 200)
        self.assertEqual(resp_reply_before.status_code, 200)
        self.assertEqual(resp_without_login.status_code, 401)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp_after.status_code, 404)
        self.assertEqual(resp_reply_after.status_code, 404)

    def test_create_message(self):
        dp = self.get_data_path("0022-another-simple-patch.json.gz")
        with open(dp, "r") as f:
            data = f.read()
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.post(
            self.PROJECT_BASE + "messages/", data, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 201)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20171023201055.21973-11-andrew.smirnov@gmail.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(
            resp.data["subject"],
            "[Qemu-devel] [PATCH v2 10/27] imx_fec: Reserve full 4K "
            "page for the register file",
        )

    def test_patch_message(self):
        the_tags = ["Reviewed-by: Paolo Bonzini <pbonzini@redhat.com"]
        dp = self.get_data_path("0022-another-simple-patch.json.gz")
        with open(dp, "r") as f:
            data = f.read()
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.post(
            self.PROJECT_BASE + "messages/", data, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 201)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20171023201055.21973-11-andrew.smirnov@gmail.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.data["tags"], [])
        resp = self.api_client.patch(
            self.PROJECT_BASE
            + "messages/20171023201055.21973-11-andrew.smirnov@gmail.com/",
            {"tags": the_tags},
        )
        self.assertEqual(resp.status_code, 200)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20171023201055.21973-11-andrew.smirnov@gmail.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.data["tags"], the_tags)

    def test_create_text_message(self):
        dp = self.get_data_path("0004-multiple-patch-reviewed.mbox.gz")
        with open(dp, "r") as f:
            data = f.read()
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.post(
            self.PROJECT_BASE + "messages/", data, content_type="message/rfc822"
        )
        self.assertEqual(resp.status_code, 201)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/1469192015-16487-1-git-send-email-berrange@redhat.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(
            resp.data["subject"],
            "[Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver",
        )

    def test_patch_series(self):
        dp = self.get_data_path("0001-simple-patch.mbox.gz")
        with open(dp, "r") as f:
            data = f.read()
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.post(
            self.PROJECT_BASE + "messages/", data, content_type="message/rfc822"
        )
        self.assertEqual(resp.status_code, 201)
        resp = self.api_client.patch(
            self.PROJECT_BASE + "series/20160628014747.20971-1-famz@redhat.com/",
            {"is_tested": True},
        )
        self.assertEqual(resp.status_code, 200)
        resp_get = self.api_client.get(
            self.PROJECT_BASE + "series/20160628014747.20971-1-famz@redhat.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertTrue(resp_get.data["is_tested"])

    def test_create_message_without_project_pk(self):
        dp = self.get_data_path("0024-multiple-project-patch.json.gz")
        with open(dp, "r") as f:
            data = f.read()
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.post(
            self.REST_BASE + "messages/", data, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["count"], 2)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(
            resp_get.data["subject"],
            "[Qemu-devel] [PATCH 1/7] SecurityPkg/Tcg2Pei: drop Tcg2PhysicalPresenceLib dependency",
        )
        resp_get2 = self.api_client.get(
            self.PROJECT_BASE_2
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get2.status_code, 200)

    def test_create_text_message_without_project_pk(self):
        dp = self.get_data_path("0023-multiple-project-patch.mbox.gz")
        with open(dp, "r") as f:
            data = f.read()
        self.api_client.login(username=self.user, password=self.password)
        resp = self.api_client.post(
            self.REST_BASE + "messages/", data, content_type="message/rfc822"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["count"], 2)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(
            resp_get.data["subject"],
            "[Qemu-devel] [PATCH 1/7] SecurityPkg/Tcg2Pei: drop Tcg2PhysicalPresenceLib dependency",
        )
        resp_get2 = self.api_client.get(
            self.PROJECT_BASE_2
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get2.status_code, 200)

    def test_without_login_create_message(self):
        dp = self.get_data_path("0022-another-simple-patch.json.gz")
        with open(dp, "r") as f:
            data = f.read()
        resp = self.api_client.post(
            self.PROJECT_BASE + "messages/", data, content_type="message/rfc822"
        )
        self.assertEqual(resp.status_code, 401)

    def test_non_maintainer_create_message(self):
        self.create_user(username="test", password="userpass")
        self.api_client.login(username="test", password="userpass")
        dp = self.get_data_path("0023-multiple-project-patch.mbox.gz")
        with open(dp, "r") as f:
            data = f.read()
        resp = self.api_client.post(
            self.REST_BASE + "messages/", data, content_type="message/rfc822"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["count"], 0)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get.status_code, 404)
        resp_get2 = self.api_client.get(
            self.PROJECT_BASE_2
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get2.status_code, 404)

    def test_maintainer_create_message(self):
        test = self.create_user(username="test", password="userpass")
        self.api_client.login(username="test", password="userpass")
        self.p.maintainers.set([test])
        dp = self.get_data_path("0023-multiple-project-patch.mbox.gz")
        with open(dp, "r") as f:
            data = f.read()
        resp = self.api_client.post(
            self.REST_BASE + "messages/", data, content_type="message/rfc822"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["count"], 1)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        resp_get2 = self.api_client.get(
            self.PROJECT_BASE_2
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get2.status_code, 404)

    def test_importer_create_message(self):
        dp = self.get_data_path("0023-multiple-project-patch.mbox.gz")
        with open(dp, "r") as f:
            data = f.read()
        self.create_user(username="test", password="userpass", groups=["importers"])
        self.api_client.login(username="test", password="userpass")
        resp = self.api_client.post(
            self.REST_BASE + "messages/", data, content_type="message/rfc822"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["count"], 2)
        resp_get = self.api_client.get(
            self.PROJECT_BASE
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(
            resp_get.data["subject"],
            "[Qemu-devel] [PATCH 1/7] SecurityPkg/Tcg2Pei: drop Tcg2PhysicalPresenceLib dependency",
        )
        resp_get2 = self.api_client.get(
            self.PROJECT_BASE_2
            + "messages/20180223132311.26555-2-marcandre.lureau@redhat.com/"
        )
        self.assertEqual(resp_get2.status_code, 200)

    def test_message(self):
        series = self.apply_and_retrieve(
            "0001-simple-patch.mbox.gz",
            self.p.id,
            "20160628014747.20971-1-famz@redhat.com",
        )

        message = series.data["patches"][0]["resource_uri"]
        resp = self.api_client.get(message)
        self.assertEqual(resp.data["mbox"], Message.objects.all()[0].get_mbox())

    def test_message_mbox(self):
        series = self.apply_and_retrieve(
            "0001-simple-patch.mbox.gz",
            self.p.id,
            "20160628014747.20971-1-famz@redhat.com",
        )

        message = series.data["patches"][0]["resource_uri"]
        resp = self.client.get(message + "mbox/")
        self.assertEqual(resp.data, Message.objects.all()[0].get_mbox())

    def test_address_serializer(self):
        data1 = {"name": "Shubham", "address": "shubhamjain7495@gmail.com"}
        serializer1 = AddressSerializer(data=data1)
        valid1 = serializer1.is_valid()
        valid_data1 = serializer1.validated_data
        data2 = {"name": 123, "address": "shubhamjain7495@gmail.com"}
        serializer2 = AddressSerializer(data=data2)
        valid2 = serializer2.is_valid()
        valid_data2 = serializer2.validated_data

        self.assertEqual(valid1, True)
        self.assertEqual(
            valid_data1,
            OrderedDict(
                [("name", "Shubham"), ("address", "shubhamjain7495@gmail.com")]
            ),
        )
        self.assertEqual(valid2, True)
        self.assertEqual(
            valid_data2,
            OrderedDict([("name", "123"), ("address", "shubhamjain7495@gmail.com")]),
        )

    def test_message_replies(self):
        series = self.apply_and_retrieve(
            "0004-multiple-patch-reviewed.mbox.gz",
            self.p.id,
            "1469192015-16487-1-git-send-email-berrange@redhat.com",
        )

        message = series.data["message"]
        resp = self.api_client.get(message + "replies/")
        self.assertEqual(resp.data["count"], 4)
        self.assertEqual(
            resp.data["results"][0]["resource_uri"],
            self.PROJECT_BASE
            + "messages/1469192015-16487-2-git-send-email-berrange@redhat.com/",
        )
        self.assertEqual(
            resp.data["results"][0]["subject"],
            "[Qemu-devel] [PATCH v4 1/2] crypto: add support for querying parameters for block encryption",
        )
        self.assertEqual(
            resp.data["results"][1]["resource_uri"],
            self.PROJECT_BASE
            + "messages/1469192015-16487-3-git-send-email-berrange@redhat.com/",
        )
        self.assertEqual(
            resp.data["results"][1]["subject"],
            "[Qemu-devel] [PATCH v4 2/2] block: export LUKS specific data to qemu-img info",
        )
        self.assertEqual(
            resp.data["results"][2]["resource_uri"],
            self.PROJECT_BASE + "messages/5792265A.5070507@redhat.com/",
        )
        self.assertEqual(
            resp.data["results"][2]["subject"],
            "Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver",
        )
        self.assertEqual(
            resp.data["results"][3]["resource_uri"],
            self.PROJECT_BASE
            + "messages/e0858c00-ccb6-e533-ee3e-9ba84ca45a7b@redhat.com/",
        )
        self.assertEqual(
            resp.data["results"][3]["subject"],
            "Re: [Qemu-devel] [PATCH v4 0/2] Report format specific info for LUKS block driver",
        )

    def test_schema(self):
        resp = self.api_client.get(self.REST_BASE + "schema/")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    main()
