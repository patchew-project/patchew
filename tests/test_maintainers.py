#!/usr/bin/env python3
#
# Copyright 2022 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from api.models import Message, WatchedQuery, QueuedSeries

from .patchewtest import PatchewTestCase, main


class MaintainerQueueTest(PatchewTestCase):
    def setUp(self):
        self.testuser = self.create_user("test", "1234", groups=["importer"])
        self.create_superuser()
        self.cli_login()
        self.add_project("QEMU", "qemu-devel@nongnu.org")

    def test_watched_query(self):
        wq = WatchedQuery(user=self.testuser, query="to:qemu-block@nongnu.org")
        wq.save()
        self.cli_import("0001-simple-patch.mbox.gz")
        msg = Message.objects.first()
        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert q
        assert q.message.id == msg.id

    def test_update_watch_on_merge_change(self):
        wq = WatchedQuery(user=self.testuser, query="to:qemu-block@nongnu.org -is:merged")
        wq.save()
        self.cli_import("0001-simple-patch.mbox.gz")
        msg = Message.objects.first()
        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert q
        assert q.message.id == msg.id

        msg.set_merged()
        msg.save()
        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert not q

    def test_update_watch_on_queue_add(self):
        wq = WatchedQuery(user=self.testuser, query="to:qemu-block@nongnu.org -nack:test")
        wq.save()
        self.cli_import("0001-simple-patch.mbox.gz")
        msg = Message.objects.first()
        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert q
        assert q.message.id == msg.id

        # TODO: support and use REST API
        self.client.post("/login/", {"username": "test", "password": "1234"})
        self.client.get("/mark-as-rejected/" + msg.message_id + "/")
        query = QueuedSeries.objects.filter(user=self.testuser, name="reject")
        q = query.first()
        assert q
        assert q.message.id == msg.id

        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert not q

    def test_update_watch_on_queue_remove(self):
        self.cli_import("0001-simple-patch.mbox.gz")
        msg = Message.objects.first()

        # TODO: support and use REST API; same below
        self.client.post("/login/", {"username": "test", "password": "1234"})
        self.client.get("/mark-as-rejected/" + msg.message_id + "/")
        query = QueuedSeries.objects.filter(user=self.testuser, name="reject")
        q = query.first()
        assert q
        assert q.message.id == msg.id

        wq = WatchedQuery(user=self.testuser, query="to:qemu-block@nongnu.org -nack:test")
        wq.save()
        self.client.get("/clear-reviewed/" + msg.message_id + "/")
        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert q
        assert q.message.id == msg.id

    def test_update_watch_with_user_me(self):
        wq = WatchedQuery(user=self.testuser, query="to:qemu-block@nongnu.org -nack:me")
        wq.save()
        self.cli_import("0001-simple-patch.mbox.gz")
        msg = Message.objects.first()
        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert q
        assert q.message.id == msg.id

        # TODO: support and use REST API
        self.client.post("/login/", {"username": "test", "password": "1234"})
        self.client.get("/mark-as-rejected/" + msg.message_id + "/")
        query = QueuedSeries.objects.filter(user=self.testuser, name="reject")
        q = query.first()
        assert q
        assert q.message.id == msg.id

        query = QueuedSeries.objects.filter(user=self.testuser, name="watched")
        q = query.first()
        assert not q


if __name__ == "__main__":
    main()
