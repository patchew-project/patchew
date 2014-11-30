FROM fedora:20
RUN yum install -y python pymongo mongodb-server offlineimap
COPY . /opt/patchew
EXPOSE 8080
CMD cd /opt/patchew; ./patchew server
