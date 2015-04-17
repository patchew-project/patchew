#!/bin/bash
set -e
ip=${1?"usage: $0 <remote address> [<username>]"}
remote=root@$ip

echo
echo "Run from the project root, press enter to continue..."
read

echo "Copying to remote..."
rsync -azr . $remote:/tmp/patchew-deploy/
echo "Installing..."
ssh $remote "cd /tmp/patchew-deploy; rm -rf build; python setup.py install"
echo "Starting service..."
ssh $remote "systemctl restart patchew"

echo -n "Testing if service has started..."
sleep 1
curl -s $ip >/dev/null && echo " yes"
