# Copyright (c) 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from distutils.spawn import find_executable

import logging
import os
import subprocess
import tempfile
import unittest

from fbtftp.base_handler import ResponseData, BaseHandler
from fbtftp.base_server import BaseServer


class FileResponseData(ResponseData):
    def __init__(self, path):
        self._size = os.stat(path).st_size
        self._reader = open(path, 'rb')

    def read(self, n):
        return self._reader.read(n)

    def size(self):
        return self._size

    def close(self):
        self._reader.close()


class StaticHandler(BaseHandler):
    def __init__(self, server_addr, peer, path, options, root, stats_callback):
        self._root = root
        BaseHandler.__init__(
            self, server_addr, peer, path, options, stats_callback
        )

    def get_response_data(self):
        return FileResponseData(os.path.join(self._root, self._path))


class StaticServer(BaseServer):
    def __init__(self, address, port, retries, timeout, root, stats_callback):
        self._root = root
        self._stats_callback = stats_callback
        BaseServer.__init__(self, address, port, retries, timeout)

    def get_handler(self, server_addr, peer, path, options):
        return StaticHandler(
            server_addr, peer, path, options, self._root, self._stats_callback
        )


def busyboxClient(filename, blksize=1400, port=1069):
    # We use busybox cli to test various bulksizes
    p = subprocess.Popen(
        [
            find_executable('busybox'),
            'tftp',
            '-l',
            '/dev/stdout',
            '-r',
            filename,
            '-g',
            '-b',
            str(blksize),
            'localhost',
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = p.communicate(timeout=1)
    return (stdout, stderr, p.returncode)


class integrationTest(unittest.TestCase):
    def setUp(self):
        logging.getLogger().setLevel(logging.DEBUG)
        # search for busybox on PATH, if not present we skip this integration
        # test.
        if not find_executable('busybox'):
            self.skipTest(
                'busybox binary not present, install it if you want to run '
                'integration tests'
            )

        self.tmpdirname = tempfile.TemporaryDirectory()
        logging.info("Created temporary directory %s" % self.tmpdirname)

        self.tmpfile = '%s/%s' % (self.tmpdirname.name, 'test.file')
        self.tmpfile_data = os.urandom(512 * 5)
        with open(self.tmpfile, 'wb') as fout:
            fout.write(self.tmpfile_data)

        self.called_stats_times = 0

    def tearDown(self):
        self.tmpdirname.cleanup()

    def stats(self, data):
        logging.debug("Inside stats function")
        self.assertEqual(data.peer[0], '127.0.0.1')
        self.assertEqual(data.file_path, self.tmpfile)
        self.assertEqual({}, data.error)
        self.assertGreater(data.start_time, 0)
        self.assertTrue(data.packets_acked == data.packets_sent - 1)
        self.assertEqual(2560, data.bytes_sent)
        self.assertEqual(
            round(data.bytes_sent / self.blksize), data.packets_sent - 1
        )
        self.assertEqual(0, data.retransmits)
        self.assertEqual(self.blksize, data.blksize)
        self.called_stats_times += 1

    def testDownloadBulkSizes(self):
        for b in (512, 1400):
            self.blksize = b
            server = StaticServer(
                '::',
                0,  # let the kernel decide the port
                2,
                2,
                self.tmpdirname,
                self.stats
            )
            child_pid = os.fork()
            if child_pid:
                # I am the parent
                try:
                    (p_stdout, p_stderr, p_returncode) = busyboxClient(
                        self.tmpfile,
                        blksize=self.blksize,
                        # use the port chosen for the server by the kernel
                        port=server._listener.getsockname()[1]
                    )
                    self.assertEqual(0, p_returncode)
                    if p_returncode != 0:
                        self.fail((p_stdout, p_stderr, p_returncode))
                    self.assertEqual(self.tmpfile_data, p_stdout)
                finally:
                    os.kill(child_pid, 15)
                    os.waitpid(child_pid, 0)
            else:
                # I am the child
                try:
                    server.run()
                except KeyboardInterrupt:
                    server.close()
                self.assertEqual(1, self.called_stats_times)
