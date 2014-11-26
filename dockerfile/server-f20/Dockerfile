FROM fedora:20
RUN yum install -y python pymongo mongodb-server offlineimap
RUN git clone https://github.com/famz/patchew.git /tmp/patchew
RUN python /tmp/patchew/setup.py install
