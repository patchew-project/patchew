FROM fedora:22
EXPOSE 8383
RUN dnf install -y findutils git mb2md python-pymongo python-cherrypy python-bottle msmtp
ADD . /opt/patchew
CMD /opt/patchew/scripts/patchew-server.sh
