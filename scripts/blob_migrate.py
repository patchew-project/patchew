#! /usr/bin/env python3

from api.models import Message, Project
from django.db import transaction

def doit(n=1000):
    done = 0
    for p in Project.objects.all():
        start = Message.objects.filter(project=p, mbox_bytes=None).order_by("-date").first()
        while start:
            first_date = start.date
            print(done, p, first_date)
            with transaction.atomic():
                previously = done
                q = Message.objects.filter(project=p, date__lte=first_date, mbox_bytes=None).order_by("-date")[:n]
                for msg in q:
                    try:
                        msg.mbox_bytes = msg.mbox.encode("utf-8")
                        msg.save()
                        done += 1
                    except Exception as e:
                        print(msg, type(e))
                    start = msg
                if done == previously and start.date == first_date:
                    start = None
