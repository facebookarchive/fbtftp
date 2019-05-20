#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest

from fbtftp.netascii import NetasciiReader
from fbtftp.base_handler import StringResponseData


class testNetAsciiReader(unittest.TestCase):
    def testNetAsciiReader(self):
        tests = [
            # content, expected output
            (
                "foo\nbar\nand another\none",
                bytearray(b"foo\r\nbar\r\nand another\r\none"),
            ),
            (
                "foo\r\nbar\r\nand another\r\none",
                bytearray(b"foo\r\x00\r\nbar\r\x00\r\nand another\r\x00\r\none"),
            ),
        ]
        for input_content, expected in tests:
            with self.subTest(content=input_content):
                resp_data = StringResponseData(input_content)
                n = NetasciiReader(resp_data)
                self.assertGreater(n.size(), len(input_content))
                output = n.read(512)
                self.assertEqual(output, expected)
                n.close()

    def testNetAsciiReaderBig(self):
        input_content = "I\nlike\ncrunchy\nbacon\n"
        for _ in range(5):
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
        self.assertEqual(input_content.count("\n"), output.count(b"\r\n"))
        n.close()
