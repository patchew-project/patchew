#!/bin/bash
set -e
remote=${1?"usage: $0 <ssh_remote> [docker_command]"}
DOCKER=${2:-sudo docker}

if ! test -f README.md; then
    echo "Must run from project root (where README.md is)"
    exit 1
fi

rsync -azrC . $remote:/tmp/patchew-deploy
ssh -t $remote "\
    mkdir -p /data/db/patchew; \
    $DOCKER stop patchew-server patchew-mongo; \
    $DOCKER rm -f patchew-server patchew-mongo; \
    cd /tmp/patchew-deploy; \
    $DOCKER rmi patchew-server; \
    $DOCKER build -t patchew-server .; \
    $DOCKER run --name patchew-mongo -v /data/db/patchew:/data/db -d mongo; \
    sleep 3; \
    $DOCKER run --name patchew-server --link patchew-mongo:mongo \
    -v \$HOME/.ssh:/root/host-ssh \
    -p 8383:8383 -d patchew-server"
