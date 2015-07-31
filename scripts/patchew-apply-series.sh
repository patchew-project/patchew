#!/bin/bash

cd $(dirname $0)/..

set -e
PATCHEW=${PATCHEW:-./patchew}
QEMU="$HOME/qemu"
remote=git@github.com:famz/qemu-patchew
remote_pub=https://github.com/famz/qemu-patchew
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

gen-git-branches()
{
    local s=$($PATCHEW query -n 1 is:complete \!has:can-apply --format=id)
    if test -z "$s"; then
        return 1
    fi
    echo "Trying to apply $s"
    $PATCHEW query -f short id:"$s"
    $PATCHEW query "id:$s" -f patches > /tmp/$$.patch
    $GIT branch | grep -q "$s" && $GIT branch -D "$s" &>/dev/null
    $GIT checkout master -b "$s"
    if $GIT am -m /tmp/$$.patch; then
        echo "Pushing branch $s"
        $GIT push -f patchew-remote "$s"
        $PATCHEW set-status -i "$s" can-apply yes
        $PATCHEW set-status -i "$s" git-repo $remote_pub
        $PATCHEW set-status -i "$s" git-branch "$s"
        $PATCHEW set-status -i "$s" git-url "https://github.com/famz/qemu-patchew/commits/$s"
    else
        $PATCHEW set-status -i "$s" can-apply no
    fi
    rm /tmp/$$.patch
}

git -C $QEMU checkout -f master
git -C $QEMU pull
cp -Hr $QEMU $tmp_repo
$GIT remote remove patchew-remote &>/dev/null || true
$GIT remote add patchew-remote $remote
$GIT push patchew-remote master
while gen-git-branches; do
    $GIT am --abort &>/dev/null || true
    $GIT reset --hard master
done
