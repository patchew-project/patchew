FROM fedora:22
EXPOSE 8383
RUN dnf install -y findutils git wget mb2md python-pymongo python-cherrypy python-bottle msmtp
RUN git clone https://github.com/qemu/qemu /qemu
ADD . /opt/patchew
CMD /opt/patchew/scripts/patchew-server.sh
