#!/bin/bash

cd $(dirname $0)/..

set -e
PATCHEW=${PATCHEW:-./patchew}
QEMU="$HOME/qemu"
tag_remote=git@github.com:famz/qemu-patchew
tmp_repo=/var/tmp/qemu-tmp
GIT="git -C $tmp_repo"
test -d $tmp_repo && rm -rf $tmp_repo

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
        $PATCHEW set-status -i "$s" git-url "https://github.com/famz/qemu-patchew/tree/$s"
    else
        $PATCHEW set-status -i "$s" can-apply no
    fi
    rm /tmp/$$.patch
}

git -C $QEMU pull
cp -Hr $QEMU $tmp_repo
$GIT checkout master
$GIT tag -d base.$$ &>/dev/null || true
$GIT tag base.$$
while gen-git-tags; do
    $GIT am --abort &>/dev/null || true
    $GIT reset --hard base.$$
done
$GIT tag -d base.$$
$GIT remote remove tag-remote 2>&1 || true
$GIT remote add tag-remote $tag_remote
$GIT push -f tag-remote --tags
