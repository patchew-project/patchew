# patchew

A patch email tracking and testing system

## Motivation

In some open source projects, people collaborate on mailing lists, where all
changes are submitted as patches. Some of such mailing lists have high activity
volumns as it's getting more popular, thus it's becoming hard for project
maintainers to track all the submitted patches: Which patches have been merged?
Which don't apply to mainline anymore due to conflicts, and need a rebase?
Which break compiling or sanity tests?  Which violate coding style conventions
such as 80 columns line limit? And which patches has no problem with these
basic checks, but is waiting for proper reviewing? These are mechanical but
tedious routine work, even before the patches get actual reviewing.

This project, `patchew` (/pæ'tʃu:/), is built to _chew_ the _patches_
automatically before they get digested by committers.

## Quick start

The program is written in Python 2.7, with a few dependencies:

  1. A `MongoDB` is required on the server as the currently supported database.

  2. You also need `pymongo` to run `patchew`. (That is also a dependency for
     "tester" subcommand, although this can be improved in the future.)

  3. Docker is required to run tester.

To get the code, clone from git repo:

```
git clone https://github.com/famz/patchew.git
cd patchew
```

Everything is done with the command `patchew`, it has several subcommands:

### Server

To run the server:

```
./patchew server
```

A server program to export a few web pages to show the patch list. The patches
are imported into the server database on background, independently. It also
shows their statuses, such as: whether the series is replied, reviewed,
appliable to current mainline, and also the result of automated compiling and
testing.

It also responds to testers (see below) through a simple custom `JSON`
interface over HTTP.

### Import

To run the importer:

```
./patchew import [-r] YOUR_MAILS[,MORE_MAILS...]
```

A command to feed some emails (either in `mbox` or `maildir` format) to the
database. It's so easy to use that I don't know how to explain it. And in order
to get real time index of mailing list patches, you should probably cron it or
use a endless loop:

```
#!/bin/bash
mdir=~/.mail/patchew/qemu-devel
while :; do
    date
    timeout --kill=30 300 offlineimap
    for i in `ls $mdir/new/* 2>/dev/null`; do
        ./patchew import "$i"
        mv "$i" $mdir/cur
    done
    sleep 60
done 2>&1 | tee patchew-fetch.log

```

### Tester

To run the tester (`sudo` for running docker, or configure docker so you can
run it as normal user):

```
sudo ./patchew tester -s http://localhost:8080/ -C /var/tmp/qemu.git -t /bin/true -i patchew:fedora-20 -L
```

It asks the `patchew` server for some patches to test. If there is no more
patches to test, it does nothing. Otherwise it will apply the patches on the
mainline's clone, spin up a docker instance (for security reason, you don't
want to try untrusted code from the patch on your machine), hand over the
applied code to the container, and let it start tests. If an error occurs in
above steps, it reports the failure to server. Otherwise it tells the server
the test passes.

#### Testing

Use `-t $test_script` to tell tester how to test the patches. The script will
be copied into the container, and started once the container started.

The script gets one argument when executed, which is the path of the testing
directory. In the directory there are a few subdirectories:

- git: the git checkout directory, whose HEAD points to the top of applied
  series, and a branch named "patchew-base" is the base branch this series
  applies on top

- patches: a dir containing the patches in mbox format

- step: a text file to output test steps as they go on, each line is a step.
  Useful to report failure step.

#### Docker

Docker is used to avoid running untrusted code in tester's environment.

##### Image

You have to prepare a docker image in which the code will be tested.

It's good to use a commonly available image such as ubuntu or fedora, with
package customizations. Such as:

1. `docker pull fedora`
2. `docker run -i -t fedora:20 /bin/bash`
3. `yum install -y $your_packages` in the container.
4. `docker ps` to find your container id.
5. `docker commit $your_container_id $my_image_name:$my_tag`

Then you can pass `-i $my_image_name:$my_tag` to `tester`.

It is even better to write your own Dockerfile to make these steps more
repeatable. This repo has a docker file example in `dockerfile/qemu-f20/`.
To build a docker image according to it:

```
docker build -t $my_image_name:$my_tag dockerfile/qemu-f20/
```

For more information please see [www.docker.com].

##### sudo

`sudo` is required in order to run docker, alternatively you can configure docker
to [run it as normal privilege](https://docs.docker.com/installation/ubuntulinux/#giving-non-root-access).

#### Log

Of course testing logs are recorded, you can see them on the server page. Your
test script doesn't have to do explicit logging, because its stdout and stderr
are captured by tester.

#### Multiple testers

You can start multiple testers on one or multiple hosts, they should not
interfere each other.

#### Speed up git clone

For each patch series to test, tester will do a `git clone` to get the latest
mainline code. This step is quicker if you clone from a local directory, add
the mainline code base as a remote (`git remote add`), then fetch from it.

To do this, add `-C LOCAL_GIT_DIR` option to `tester` command.

## TODO list

### Notification

Notification can be easily done, in wrong ways.

It would be convenient to automatically reply to the mailing list if we catch
some flaws in the series, but it can also be very noisy if do it without care.
People want information, not noise. We'll add email notification once we are
confident in telling information from noise in this system.

### Git repo

What's easier than cloning from a git repo when you want to try a patch series
that has not been merged yet? Asking Bob from next door to do it for you,
probably.

### Import through HTTP `JSON` interface

This will further decouple server and importer.

### Tester authentication

Currently the server trusts the result from any tester. Probably not a good
idea if the server is on untrusted network.

### Code base

The server advises the code base on which the tester should apply the patches.
This is currently hard coded and only knows about [qemu.git](http://qemu-project.org).

### Warning

Sometimes a test should pass, even with some warnings.

Coding style is probably one example where warning is better than error: we are
told to only do one thing in a patch. When you change a code which is wrong
both in coding style and logic, but you don't care about the coding style
because you are not as sensitive as your loyal checker script, it's very late
and you decide to only fix the logic. That's the right thing to do:

```
-            if ((ret = blk_read(blk, mbr[i].start_sector_abs, data1, 1)) > 0) {
+            if ((ret = blk_read(blk, mbr[i].start_sector_abs, data1, 1)) < 0) {
```

But if you want to keep the coding style checker happy you have to do:

```
-            if ((ret = blk_read(blk, mbr[i].start_sector_abs, data1, 1)) > 0) {
+            ret = blk_read(blk, mbr[i].start_sector_abs, data1, 1);
+            if (ret < 0) {
```

Or split this simple patch to two patches, write two commit messages and send two emails.

Or just go to bed and leave it to Bob the poor guy.

*It's only one example where machines are machines. Although we always want our
machines to do more things for us, there is one thing machines just can't do
yet: reading our mind. It's a question of philosophy about automation and UI
design: when you build a machine and rely on it for something, keep in mind
that machines will go wrong because they are built by imperfect persons, then
leave room for human to fix it when it is wrong.*
