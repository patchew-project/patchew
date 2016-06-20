#!/bin/bash
set -e
if [ $# -lt 2 ]; then
    echo "usage: $0 <remote> <type>"
    echo
    echo "Types can be 'server', 'importer', 'tester'"
    exit 1
fi

remote="$1"
dt="$2"

DOCKER=${DOCKER:-"sudo docker"}

if ! test -f README.md; then
    echo "Must run from project root"
    exit 1
fi

if ! test -f $dt.docker; then
    echo "Unknown instance type"
    exit 1
fi

REMOTE_COPY=/tmp/patchew-deploy
rsync --exclude=.git --delete -azrC . $remote:$REMOTE_COPY

importer_setup()
{
    local conf="$HOME/.patchew-importer/config"
    if ! test -f "$conf"; then
        # Generate default config
        mkdir -p $(dirname "$conf")
        cat >$conf <<EOF
# Patchew importer deploy config:
PATCHEW_SERVER=http://localhost:8000
PATCHEW_UESR=somebody
PATCHEW_PASS=password001

# Imap setting to fetch email
IMAP_SERVER=imap.gmail.com
IMAP_USER=myusername
IMAP_PASS=mypassword
IMAP_SSL=yes
# SHA1 fingerprint of the imap server certificate
IMAP_CERT_FINGERPRINT=
IMAP_FOLDERS=qemu-devel

IMAP_DELETE_AFTER_IMPORT=

EOF
    fi
    cp $conf $conf.new
    $EDITOR $conf.new
    if test -z "$(cat $conf.new)"; then
        echo "empty config, quit"
        rm $conf.new
    fi
    mv $conf.new $conf
    scp $conf $remote:$REMOTE_COPY/patchew-importer.config
}

case "$dt" in
    "importer")
        importer_setup
        ;;
    "server")
        # TODO
        ;;
    "tester")
        ;;
    *)
        echo "Uknown type"
        exit 1
        ;;
esac

ssh -t $remote "\
    $DOCKER stop patchew-$dt 2>/dev/null; \
    $DOCKER rm -f patchew-$dt 2>/dev/null; \
    $DOCKER tag patchew:$dt patchew:$dt-prev 2>/dev/null; \
    cd $REMOTE_COPY; \
    $DOCKER build -t patchew:$dt -f $dt.docker .; \
    $DOCKER run --name patchew-$dt \
        -d \
        $extra_opts \
        patchew:$dt; \
    $DOCKER rmi patchew:$dt-prev 2>/dev/null;
    cd /;
    rm $REMOTE_COPY -rf"
