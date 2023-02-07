# Patchew Documentation

## About

Patchew, pronounced as /pæ'tʃu:/, is a system built to automatically _chew_
patches that are submitted as emails on mailing lists.

## What can it do, exactly?

It can:

 - Collect and index the patch series.
 - Apply the patch series on top of git master, and push to a git remote.
 - Trigger customizable tests when a series appears.
 - Support multiple testers with that run in different environments.
 - Send email notification when a test fails.
 - Recognize various statuses (picking up "Reviewed-by", "Tested-by", etc.) of
   the patch series from the patch email and replies.
 - Search or apply series from the command line.
 - Deploy your server to [openshift](https://openshift.redhat.com) instantly.
 - Manage multiple projects with separate configurations.

## Submit a feature request or a bug report

[https://github.com/patchew-project/patchew/issues/new](https://github.com/patchew-project/patchew/issues/new)

Alternatively, send an email to patchew-devel@redhat.com if you prefer so.

## Submit a patch

We accept PR on github for one-off/small contributions but it is encouraged to
submit your patches with git-send-email to the Patchew development and
discussion mailing list, patchew-devel@redhat.com.

## Installing

Patchew can be installed in a podman container; it is possible to connect
the container to a webserver running on the host via either port 80 or a
FastCGI socket.

Either SQLite or PostgreSQLcan be used as the database backend; the latter
requires a separate container.

The `scripts/deploy` scripts is a wrapper script that uses Ansible to
install the various components of Patchew.  For example:

```
# ./scripts/deploy --db localhost
# systemctl enable patchew-server-db
# ./scripts/deploy --server localhost
# systemctl enable patchew-server
```

A sample nginx configuration is as follows:

```
upstream patchew-server {
    server unix:/data/patchew-server/data/nginx.sock fail_timeout=0;
}

server {
    server_name patchew.org;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header Host            $host;
    location / {
      proxy_pass http://patchew-server;
    }
    proxy_connect_timeout       600;
    proxy_send_timeout          600;
    proxy_read_timeout          600;
    send_timeout                600;
    client_max_body_size 100M;
}
```

## Known issues

 - Binary patches are not recognized correctly.

## License

See LICENSE file.
