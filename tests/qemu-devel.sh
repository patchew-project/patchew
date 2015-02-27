#!/bin/bash
# The MIT License (MIT)
#
# Copyright (c) 2014 Fam Zheng <fam@euphon.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

set -e
MAKEOPTS=-j4

# $1 is the path to the test directory, where the following items are
# contained:
#
# - git: the git checkout directory, whose HEAD points to the applied series,
# and a branch named "patchew-base" is the base this series applies on top
#
# - patches: a dir containing the patches in mbox format
#
# - step: a text file to record test steps as they go on, each line is a step.
# Useful to report failure step.
stepfile="$1/step"

cd $1

step()
{
    echo
    echo "*** Testing '$1' ***"
    echo
    echo "$1" >> $stepfile
}

# run command and if it fails, write a WARNING message
warn_run()
{
    if ! $@ &>/tmp/warn-run-$$; then
        (
        echo "command failed with exit code $?"
        echo '$@'
        cat /tmp/warn-run-$$
        ) | sed -e 's/^/<<< WARNING >>>/'
    else
        cat /tmp/warn-run-$$
    fi
}

cd patches
step "coding style check"
for f in *.patch; do
    echo "Checking $f"
    warn_run ../git/scripts/checkpatch.pl $f
    echo
done
cd ..

mkdir build
cd build

step "configure"
../git/configure --target-list=x86_64-softmmu

step "compile"
make $MAKEOPTS

step "make check"
make check $MAKEOPTS

#step "make check-block"
#make check-block $MAKEOPTS
