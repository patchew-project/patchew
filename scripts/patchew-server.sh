#!/bin/bash

cd $(dirname $0)/..

PATCHEW="./patchew --db mongo://$MONGO_PORT_27017_TCP_ADDR:$MONGO_PORT_27017_TCP_PORT/patchew"
$PATCHEW server &
MBOX_FOLDER="ftp://lists.gnu.org/qemu-devel"

import()
{
    local OUT=/tmp/patchew-maildir.$$
    mb2md -s $(realpath $1) -d $OUT
    find $OUT -type f -exec $PATCHEW import {} \;
    rm -rf $OUT
}

while :; do
    for i in 0 1; do
        cp mbox-$i mbox-$i-old
        if wget -c -O mbox-$i $MBOX_FOLDER/$(date "--date=$(date +%Y-%m-15) -$i months" +%Y-%m); then
            if ! cmp mbox-$i-old mbox-$i; then
                import mbox-$i
                scripts/patchew-apply-series.sh
            fi
            rm mbox-$i-old
        fi
        sleep 300
    done
done
