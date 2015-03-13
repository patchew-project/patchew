#!/bin/bash

while :; do
	#(cd $HOME/qemu; git pull)
	timeout -k 4000 3600 sudo ./patchew tester -s http://127.0.0.1/ \
		-i test -p fef87abed8f52d7b9fa7899421b1fc4f \
		-C $HOME/work/qemu -d patchew:tester-qemu \
		-t tests/qemu-devel.sh
	sleep 5
done
