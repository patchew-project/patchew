import unittest
import subprocess
import os
import tempfile
import time

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

class PatchewTestCase(unittest.TestCase):
    def setUp(self):
        self._port = 18383
        self._server_url = "http://127.0.0.1:%d/" % self._port
        self._log = tempfile.NamedTemporaryFile()
        self._manage_py = os.path.join(BASE_DIR, "manage.py")
        self._cli = os.path.join(BASE_DIR, "patchew-cli")
        self._superuser = "test"
        self._password = "patchewtest"

    def assert_server_running(self):
        return self._server_p.poll() == None

    def start_server(self):
        os.environ["PATCHEW_DATA_DIR"] = tempfile.mkdtemp()
        p = subprocess.check_output([self._manage_py, "migrate"])
        p = subprocess.Popen([self._manage_py, "shell"],
                             stdin=subprocess.PIPE, stdout=self._log,
                             stderr=self._log)
        p.stdin.write("from django.contrib.auth.models import User\n")
        p.stdin.write("user=User.objects.create_user('%s', password='%s')\n" % \
                      (self._superuser, self._password))
        p.stdin.write("user.is_superuser=True\n")
        p.stdin.write("user.is_staff=True\n")
        p.stdin.write("user.save()\n")
        p.stdin.close()
        p.wait()
        self._server_p = subprocess.Popen([self._manage_py, "runserver",
                                          str(self._port)],
                                          stdout=self._log, stderr=self._log)
        ok = False
        for i in range(20):
            rc = subprocess.call(["curl", self._server_url],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if rc == 0:
                ok = True
                break
            time.sleep(0.05)
        assert ok
        self.assert_server_running()

    def stop_server(self):
        self._server_p.terminate()

    def cli_command(self, *argv):
        return subprocess.check_output([self._cli, "-s", self._server_url] +\
                                        list(argv))

def main():
    return unittest.main()
