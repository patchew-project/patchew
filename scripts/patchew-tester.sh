#!/bin/bash

while :; do
	#(cd $HOME/qemu; git pull)
	timeout -k 4000 3600 sudo patchew tester -s http://127.0.0.1/ \
		-i os1 -p 6a54f68ae290a64b6db156b50a25f756 \
		-C $HOME/work/qemu -d patchew:tester-qemu \
		-t tests/qemu-devel.sh
	sleep 5
done
