#!/bin/bash

cd $(dirname $0)/..

PATCHEW="./patchew --db mongo://$MONGO_PORT_27017_TCP_ADDR:$MONGO_PORT_27017_TCP_PORT/patchew"
$PATCHEW server &
MBOX_FOLDER="ftp://lists.gnu.org/qemu-devel"
QEMU='$HOME/qemu'
local tag_remote=git@github.com:famz/qemu-patchew
local repo=/var/tmp/qemu.$$
local GIT="git -C $repo"
test -d $repo && rm -rf $repo

import()
{
    local OUT=/tmp/patchew-maildir.$$
    mb2md -s $(realpath $1) -d $OUT
    find $OUT -type f -exec $PATCHEW import {} \;
    rm -rf $OUT
}

gen-git-tags()
{
    local s=$($PATCHEW query -n 1 is:complete \!has:can-apply --format=id)
    if test -z "$s"; then
        return 1
    fi
    echo "Trying to apply $s"
    $PATCHEW query -f short id:"$s"
    $PATCHEW query "id:$s" -f patches > /tmp/$$.patch
    if $GIT tag | grep -q "$s" || $GIT am /tmp/$$.patch; then
        $GIT tag "$s"
        $PATCHEW set-status -i "$s" can-apply yes
        $PATCHEW set-status -i "$s" git-repo $tag_remote
        $PATCHEW set-status -i "$s" git-tag "$s"
    else
        $PATCHEW set-status -i "$s" can-apply no
    fi
    rm /tmp/$$.patch
}

apply-series()
{
    git -C /qemu pull
    cp -r /qemu $repo
    while gen-git-tags; do
        git am --abort
        git reset --hard origin/master
    done
    $GIT remote add tag-remote $tag_remote
    $GIT push -f tag-remote --tags
}

while :; do
    for i in 0 1; do
        cp mbox-$i mbox-$i-old
        if wget -c -O mbox-$i $MBOX_FOLDER/$(date "--date=$(date +%Y-%m-15) -$i months" +%Y-%m); then
            if ! cmp mbox-$i-old mbox-$i; then
                import mbox-$i
                apply-series
            fi
            rm mbox-$i-old
        fi
        sleep 300
    done
done
