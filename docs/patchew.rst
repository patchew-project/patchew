Patchew design and flow
=======================

Patchew is designed around three components:

-  a web server, which hosts the Patchew user interface and also exposes
   API endpoints for use from the other parts;

-  one or more *importers*, which read email from an IMAP server, send
   them to the server, and pushes the messages to a git tree;

-  and a set of *testers*, which poll for git trees that have been
   pushed and runs a shell script on the cloned tree.

The data flow between the components can be represented as follows:

::
    
          IMAP              API
    Mail ------> Importer -----> Patchew server
    
              API                           git
    Importer ----> Unapplied series (mbox) ----> Git Server
                                         |
                                         '-----> Patchew server
                                            API
    
            API                         git        shell         API
    Tester -----> Untested series (tag) ----> Tree ----> Result -----> Patchew server

While the importer's two tasks could in principle be split to two
separate components, usually a single person can be the point of contact
for both of them. One importer can handle one or more patchew projects,
and similarly for testers. However, while one project will typically get
email from one importer only, it can be served by multiple testers (for
example for different architectures or operating systems).

Setting up patchew
==================

Deploying the server
--------------------

The server runs in a Docker container.  You can deploy it using
``scripts/deploy``, which is a wrapper for Ansible::

    ./scripts/deploy -s root@patchew.example.com

All unrecognized options are passed directly to Ansible.  For example,
if you do not have public key access configured on the host, add "-k".

We suggest placing a proxy in front of the server. (why...)

Creating users
--------------

-  Create importer user

-  Create tester user

-  Create maintainer user

Creating a project
------------------

(TODO)

Configuring git plugin
----------------------

??? Can you configure the git plugin *after* the importer has been
created ???

Deploying the importer
----------------------

Like the server, the importer service runs in a Docker container.
You can deploy the importer using the same ``scripts/deploy`` wrapper
for Ansible::

    ./scripts/deploy -i root@patchew.example.com

As before, if you do not have public key access configured on the host,
add "-k".  If the IMAP server uses TLS, you need to retrieve the
fingerprint for the IMAP server's certificate::

    openssl s_client -connect imap.gmail.com:993 |   \
        openssl x509 -fingerprint |                  \
        grep Fingerprint

(you may need to add ``-starttls imap`` to the ``openssl s_client``
command line).  Note that the fingerprint format, as printed by
``openssl x509 -fingerprint``, looks like a sequence of hexadecimal
bytes separated by colons; offlineimap and thus ``scripts/deploy``
do not use colons.

You can also specify all the variables directly on the command line
using the ``-e`` option::

    ./scripts/deploy -i root@patchew.example.com -e "
        instance_name=patchew-importer-example
        patchew_server=http://patchew.example.com/
        importer_user=importer
        importer_pass=gotsomepatches
        imap_server=imap.example.com
        imap_user=username@example.com
        imap_pass=hunter2
        imap_cert_fingerprint=00112233445566778899aabbccddeeff
        imap_folders=INBOX
        imap_delete_after_import=n"

Now you can check on the remote machine that the importer is running::

    systemctl status patchew-importer-example.service

The importer starts importing messages from the IMAP server to local
storage and from there to git repo.  You can watch it with::

    journalctl -f -u patchew-importer-example

Deploying the tester
--------------------

Unlike the importer and server, the tester does not run in a container;
it is simply a cron job on one or more hosts. Like the importer and
server, however, testers are deployed via ``scripts/deploy`` and
Ansible::

    ./scripts/deploy -t root@patchew-tester1.example.com -e "
        instance_name=patchew-tester1
        patchew_server=http://patchew.example.com/
        tester_user=tester
        tester_pass=wantsomepatches
        tester_project=frobnicator"

The cron job runs as a user named "patchew".

Continuous integration
======================

Testing
-------

"More information about xxx..." -> Login -> ...

Requirements
~~~~~~~~~~~~

(TODO)

Email notifications
-------------------

Events
~~~~~~

(TODO)

Templates
~~~~~~~~~

(TODO)
