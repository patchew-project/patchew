#!/bin/bash

cd $(dirname $0)
cd ..

PATCHEW="./patchew --db mongo://$MONGO_PORT_27017_TCP_ADDR:$MONGO_PORT_27017_TCP_PORT/patchew"
$PATCHEW server &

import()
{
    local OUT=/tmp/patchew-maildir.$$
    mb2md -s $(realpath $1) -d $OUT
    find $OUT -exec $PATCHEW import {} \;
    rm -rf $OUT
}

while :; do
    for i in 0 1; do
        if curl --time-cond mbox-$i --remote-time \
            -o mbox-$i-new ftp://lists.gnu.org/qemu-devel/$(date "--date=$(date +%Y-%m-15) -$i months" +%Y-%m); then
            if ! cmp mbox-$i-new mbox-$i; then
                mv mbox-$i-new mbox-$i
                import mbox-$i
            else
                rm mbox-$i-new
            fi
        fi
        sleep 30
    done
done
