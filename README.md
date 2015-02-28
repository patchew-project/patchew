# patchew

A patch email tracking and testing system

This project, `patchew` (/pæ'tʃu:/), is built to automatically _chew_ the
_patches_ before they get human reviewing.

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

## See it live

This project stems from QEMU development. There is a running instance for
QEMU patches:

[http://qemu.patchew.org]

## Quick start

The program is written in Python 2.7, with a few dependencies:

  1. `MongoDB` is required on the server.

  2. You also need `pymongo` to run `patchew`. (That is also a dependency for
     "tester" subcommand, although this can be improved in the future.)

  3. Docker is required to run the tester.

  4. `bottle` and `cherrypy` for the web server. You can install both with pip.

To get the code, clone from git repo:

```
git clone https://github.com/famz/patchew.git
cd patchew
```

Then you can install commands and files to your system with:

```
sudo python setup.py install
```

All operations are done by running `patchew` subcommands.

### The Server

Make sure you have started mongodb server.

To run the server at your console:

```
patchew server
```

Or start the systemd service:

```
sudo systemctl start patchew
```

Then you can view the patch series that are imported to the mongodb by
accessing 127.0.0.1 from your browser.

It also responds to testers (see below) through a simple custom `JSON`
API interface.

#### Search

On the web page, you can search the database by keywords, testing results,
dates, with a simple search syntax. See the help message hidden aside the
search box.

### Import data

At server side, run the `import` subcommand:

```
patchew import [-r] YOUR_MAILS[,MORE_MAILS...]
```

This command feeds emails (either in `mbox` or `maildir` format) to the
database.

If you need continuously importing new emails, you can do something like this:

```
#!/bin/bash
mdir=~/mailbox-dir
while :; do

    # sync with email server
    offlineimap

    # import new messages
    for i in `ls $mdir/new/*`; do
        ./patchew import "$i"
        mv "$i" $mdir/cur
    done
done

```

### Tester

The tester runs on another host, queries for new series and test them.

```
sudo ./patchew tester -s http://localhost:8080/ -C /var/tmp/qemu.git \
    -t /bin/true -d patchew:fedora-20 -L \
    -i tester-name -p tester-token
```

It asks the `patchew` server for some patches to test. If there is no more
patches to test, it does nothing; otherwise it will apply the patches on the
mainline's clone, spin up a docker instance (for security reason, you don't
want to try untrusted code from the patch on your machine), hand over the
applied code to the container, and let it start the actual tests. If an error
occurs in above steps, it reports the failure to server. Otherwise it tells the
server the test passes, along with the testing log.


```
usage: patchew tester [-h] -s SERVER -i IDENTITY -p SIGNATURE_KEY [-t
TEST_SCRIPT] [-d DOCKER_IMAGE] [-L] [-C QUICK_REPO] [-k]

optional arguments:
  -h, --help            show this help message and exit
  -s SERVER, --server SERVER
                        Pathew server's base URL
  -i IDENTITY, --identity IDENTITY
                        Verification identity to use
  -p SIGNATURE_KEY, --signature-key SIGNATURE_KEY
                        Verification key to use
  -t TEST_SCRIPT, --test-script TEST_SCRIPT
                        Test script to run inside the container
  -d DOCKER_IMAGE, --docker-image DOCKER_IMAGE
                        Docker image to use.
  -L, --loop            Loop and repeat.
  -C QUICK_REPO, --quick-repo QUICK_REPO
                        Clone from a (faster) git repo before pulling from the server returned codebase, in order to speed up the test.
  -k, --keep-temp       Don't remove temporary directory before exit
```

_Note: `-i` and `-p` are necessary to verify the tester to the server. They can
be generated with "newid" subcommand on server side._

#### How testing works

The above command used `-t $test_script` to specify the script to test the
patches. The script will be copied into the container for execution.

The script gets one argument when executed, which is the path of the testing
directory. In the directory there are a few subdirectories:

- git: the git checkout directory, whose HEAD points to the top of applied
  series, and a branch named "patchew-base" is the base branch this series
  applies on top

- patches: a dir containing the patches in mbox format

- step: a text file to output test steps as they go on, one step name per line.
  Useful to report failure step.

#### Security

Docker is used to avoid running untrusted code in tester's environment.

##### Image

You have to prepare a docker image in which the testing runs.

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

To do this, add `-C LOCAL_GIT_DIR` option to the `tester` subcommand.

## Testing Result Notification

For simplicity the patchew server doesn't have notification framework, however
there is a configurable hook in `server.conf` that run a script after each
series is tested:

```
[hook]
post-testing = patchew-hook-post-testing {dir}
```

The scripts receives an argument (`{dir}`) which points to a directory that has
the testing result information.

The installed `patchew-hook-post-testing` is only for reference, and you
probably want to write your own.

## Other server subcommands

`newid` generates a server side signature key that can be used when tester
submits testing result. Only results signed with known signatures will be
accepted by server.

`query` will list threads with given criteria (with the same searching syntax
with the web).

`untest` clears testing result by given criteria.

`syncdb` scans all the messages in database and rebuild their metadata.

## TODO list

### Git repo

What's easier than cloning from a git repo when you want to try a patch series
that has not been merged yet? Asking Bob from next door to do it for you,
probably.

### Import through HTTP `JSON` interface

This will further decouple server and importer.

### Code base

The server advises the code base on which the tester should apply the patches.
This is currently hard coded and only knows about [qemu.git](http://qemu-project.org).
