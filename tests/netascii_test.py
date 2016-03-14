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

import unittest

from fbtftp.netascii import NetasciiReader
from fbtftp.base_handler import StringResponseData


class testNetAsciiReader(unittest.TestCase):
    def testNetAsciiReader(self):
        input_content = "foo\nbar\nand another\none"
        resp_data = StringResponseData(input_content)
        n = NetasciiReader(resp_data)
        self.assertGreater(n.size(), len(input_content))
        output = n.read(512)
        self.assertEqual(
            bytearray(b'foo\r\nbar\r\nand another\r\none'), output
        )
        n.close()

    def testNetAsciiReaderWithSlashR(self):
        input_content = "foo\r\nbar\r\nand another\r\none"
        resp_data = StringResponseData(input_content)
        n = NetasciiReader(resp_data)
        self.assertGreater(n.size(), len(input_content))
        output = n.read(512)
        self.assertEqual(
            bytearray(b'foo\r\x00\r\nbar\r\x00\r\nand another\r\x00\r\none'),
            output
        )
        n.close()

    def testNetAsciiReaderBig(self):
        input_content = "I\nlike\ncrunchy\nbacon\n"
        for i in range(5):
            input_content += input_content
        resp_data = StringResponseData(input_content)
        n = NetasciiReader(resp_data)
        self.assertGreater(n.size(), 0)
        self.assertGreater(n.size(), len(input_content))
        block_size = 512
        output = bytearray()
        while True:
            c = n.read(block_size)
            output += c
            if len(c) < block_size:
                break
        self.assertEqual(input_content.count('\n'), output.count(b'\r\n'))
        n.close()
