#!/bin/bash
set -e
ip=${1?"usage: $0 <remote address> [<username>]"}
user=${2:-root}
remote=$user@$ip
DOCKER=docker

if [ "$user" != "root" ]; then
    DOCKER="sudo docker"
fi

if ! test -f README.md; then
    echo "Must run from project root (where README.md is)"
    exit 1
fi

scp -r . $remote:/tmp/patchew-deploy.$$
ssh $remote "$DOCKER stop patchew-server; $DOCKER rm -f patchew-server; cd /tmp/patchew-deploy.$$ && $DOCKER build -t patchew-server ."
ssh $remote $DOCKER run --name patchew-mongo -d mongo || true
ssh $remote $DOCKER run --name patchew-server --link patchew-mongo:mongo -p 8383:8383 -d patchew-server
