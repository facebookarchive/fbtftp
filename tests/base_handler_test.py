#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from collections import OrderedDict
from unittest.mock import patch, Mock, call
from fbtftp.netascii import NetasciiReader
import socket
import time
import unittest

from fbtftp.base_handler import BaseHandler, StringResponseData
from fbtftp import constants


class MockSocketListener:
    def __init__(self, network_queue, peer):
        self._network_queue = network_queue
        self._peer = peer

    def recvfrom(self, blocksize):
        return self._network_queue.pop(0), self._peer


class MockHandler(BaseHandler):
    def __init__(
        self, server_addr, peer, path, options, stats_callback, network_queue=()
    ):
        self.response = StringResponseData("foo")
        super().__init__(server_addr, peer, path, options, stats_callback)
        self.network_queue = network_queue
        self.peer = peer
        self._listener = MockSocketListener(network_queue, peer)
        self._listener.sendto = Mock()
        self._listener.close = Mock()
        self._listener.settimeout = Mock()

    def get_response_data(self):
        """ returns a mock ResponseData object"""
        self._response_data = Mock()
        self._response_data.read = self.response.read
        self._response_data.size = self.response.size
        return self._response_data


class testSessionHandler(unittest.TestCase):
    def setUp(self):
        self.options = OrderedDict(
            [
                ("default_timeout", 10),
                ("retries", 2),
                ("mode", "netascii"),
                ("blksize", 1492),
                ("tsize", 0),
                ("timeout", 99),
            ]
        )

        self.server_addr = ("127.0.0.1", 1234)
        self.peer = ("127.0.0.1", 5678)
        self.handler = MockHandler(
            server_addr=self.server_addr,
            peer=self.peer,
            path="want/bacon/file",
            options=self.options,
            stats_callback=self.stats_callback,
        )

    def stats_callback(self):
        pass

    def init(self, universe=4):
        if universe == 4:
            server_addr = ("127.0.0.1", 1234)
            peer = ("127.0.0.1", 5678)
        else:
            server_addr = ("::1", 1234)
            peer = ("::1", 5678)
        handler = BaseHandler(
            server_addr=server_addr,
            peer=peer,
            path="want/bacon/file",
            options=self.options,
            stats_callback=self.stats_callback,
        )
        self.assertEqual(handler._timeout, 10)
        self.assertEqual(handler._server_addr, server_addr)
        # make sure expire_ts is in the future
        self.assertGreater(handler._expire_ts, time.time())
        self.assertEqual(handler._retries, 2)
        self.assertEqual(handler._block_size, constants.DEFAULT_BLKSIZE)
        self.assertEqual(handler._last_block_sent, 0)
        self.assertEqual(handler._retransmits, 0)
        self.assertEqual(handler._current_block, None)
        self.assertEqual(handler._should_stop, False)
        self.assertEqual(handler._path, "want/bacon/file")
        self.assertEqual(handler._options, self.options)
        self.assertEqual(handler._stats_callback, self.stats_callback)
        self.assertEqual(handler._peer, peer)
        self.assertIsInstance(handler._get_listener(), socket.socket)
        if universe == 6:
            self.assertEqual(handler._get_listener().family, socket.AF_INET6)
        else:
            self.assertEqual(handler._get_listener().family, socket.AF_INET)

    def testInitV6(self):
        self.init(universe=6)

    def testInitV4(self):
        self.init(universe=4)

    def testResponseDataException(self):
        server_addr = ("127.0.0.1", 1234)
        peer = ("127.0.0.1", 5678)
        with patch.object(MockHandler, "get_response_data") as mock:
            mock.side_effect = Exception("boom!")
            handler = MockHandler(
                server_addr=server_addr,
                peer=peer,
                path="want/bacon/file",
                options=self.options,
                stats_callback=self.stats_callback,
            )
            self.assertEqual(
                handler._stats.error, {"error_message": "boom!", "error_code": 0}
            )

    def testParseOptionsNetascii(self):
        self.handler._response_data = StringResponseData("foo\nbar\n")
        self.handler._parse_options()
        self.assertEqual(
            self.handler._stats.options_in,
            {"mode": "netascii", "blksize": 1492, "tsize": 0, "timeout": 99},
        )
        self.assertIsInstance(self.handler._response_data, NetasciiReader)
        self.assertEqual(self.handler._stats.blksize, 1492)

        # options acked by the server don't include the mode
        expected_opts_to_ack = self.options
        del expected_opts_to_ack["mode"]
        # tsize include the number of bytes in the response
        expected_opts_to_ack["tsize"] = str(self.handler._response_data.size())
        self.assertEqual(self.handler._stats.options, expected_opts_to_ack)
        self.assertEqual(self.handler._stats.options_acked, expected_opts_to_ack)
        self.assertEqual(self.handler._tsize, int(expected_opts_to_ack["tsize"]))

    def testParseOptionsBadMode(self):
        options = {
            "default_timeout": 10,
            "retries": 2,
            "mode": "IamBadAndIShoudlFeelBad",
            "blksize": 1492,
            "tsize": 0,
            "timeout": 99,
        }
        self.handler = MockHandler(
            server_addr=self.server_addr,
            peer=self.peer,
            path="want/bacon/file",
            options=options,
            stats_callback=Mock(),
        )
        self.handler._close = Mock()
        self.handler._parse_options()
        self.handler._close.assert_called_with()
        self.assertEqual(
            self.handler._stats.error["error_code"], constants.ERR_ILLEGAL_OPERATION
        )
        self.assertTrue(
            self.handler._stats.error["error_message"].startswith("Unknown mode:")
        )
        self.handler._get_listener().sendto.assert_called_with(
            # \x00\x05 == OPCODE_ERROR
            # \x00\x04 == ERR_ILLEGAL_OPERATION
            b"\x00\x05\x00\x04Unknown mode: 'IamBadAndIShoudlFeelBad'\x00",
            ("127.0.0.1", 5678),
        )

    def testClose(self):
        options = {
            "default_timeout": 10,
            "retries": 2,
            "mode": "IamBadAndIShoudlFeelBad",
            "blksize": 1492,
            "tsize": 0,
            "timeout": 99,
        }
        self.handler = MockHandler(
            server_addr=self.server_addr,
            peer=self.peer,
            path="want/bacon/file",
            options=options,
            stats_callback=Mock(),
        )

        self.handler._retransmits = 100
        self.handler._close(True)
        self.assertEqual(self.handler._retransmits, 100)
        self.handler._stats_callback.assert_called_with(self.handler._stats)
        self.handler._get_listener().close.assert_called_with()
        self.handler._response_data.close.assert_called_with()
        self.handler._on_close = Mock()
        self.handler._on_close.side_effect = Exception("boom!")
        self.handler._close(True)

    def testRun(self):
        # mock methods
        self.handler._close = Mock()
        self.handler._transmit_error = Mock()
        self.handler._parse_options = Mock()
        self.handler._transmit_oack = Mock()
        self.handler._transmit_data = Mock()
        self.handler._next_block = Mock()

        self.handler._stats.error = {"error_message": "boom!", "error_code": 0}
        self.handler.run()
        self.handler._close.assert_called_with()
        self.handler._transmit_error.assert_called_with()

        self.handler._stats.error = {}
        self.handler._should_stop = True
        self.handler.run()
        self.handler._parse_options.assert_called_with()
        self.handler._transmit_oack.assert_called_with()

        self.handler._options = {}
        self.handler.run()
        self.handler._next_block.assert_called_with()
        self.handler._transmit_data.assert_called_with()

    def testRunOne(self):
        self.handler.on_new_data = Mock()
        self.handler._handle_timeout = Mock()
        self.handler._expire_ts = time.time() + 1000
        self.handler.run_once()
        self.handler.on_new_data.assert_called_with()

        self.handler._expire_ts = time.time() - 1000
        self.handler.run_once()
        self.handler.on_new_data.assert_called_with()
        self.handler._handle_timeout.assert_called_with()

    def testOnNewDataHandleAck(self):
        self.handler = MockHandler(
            server_addr=self.server_addr,
            peer=self.peer,
            path="want/bacon/file",
            options=self.options,
            stats_callback=self.stats_callback,
            # client acknolwedges DATA block 1, we expect to send DATA block 2
            network_queue=[b"\x00\x04\x00\x01"],
        )
        self.handler._last_block_sent = 1
        self.handler.on_new_data()
        self.handler._get_listener().settimeout.assert_has_calls(
            [call(self.handler._timeout), call(None)]
        )
        # data response sohuld look like this:
        #
        #    2 bytes       2 bytes      n bytes
        #  ---------------------------------------
        #  | Opcode = 3 |   Block #  |   Data    |
        #  ---------------------------------------
        self.handler._get_listener().sendto.assert_called_with(
            # client acknolwedges DATA block 1, we expect to send DATA block 2
            b"\x00\x03\x00\x02foo",
            ("127.0.0.1", 5678),
        )

    def testOnNewDataTimeout(self):
        self.handler._get_listener().recvfrom = Mock(side_effect=socket.timeout())
        self.handler.on_new_data()
        self.assertFalse(self.handler._should_stop)
        self.assertEqual(self.handler._stats.error, {})

    def testOnNewDataDifferentPeer(self):
        self.handler._get_listener().recvfrom = Mock(
            return_value=(b"data", ("1.2.3.4", "9999"))
        )
        self.handler.on_new_data()
        self.assertTrue(self.handler._should_stop)

    def testOnNewDataOpCodeError(self):
        error = b"\x00\x05\x00\x04some_error\x00"
        self.handler._get_listener().recvfrom = Mock(return_value=(error, self.peer))
        self.handler.on_new_data()
        self.assertTrue(self.handler._should_stop)
        self.handler._get_listener().sendto.assert_called_with(error, self.peer)

    def testOnNewDataNoAck(self):
        self.handler._get_listener().recvfrom = Mock(
            return_value=(b"\x00\x02\x00\x04", self.peer)
        )
        self.handler.on_new_data()
        self.assertTrue(self.handler._should_stop)
        self.assertEqual(
            self.handler._stats.error,
            {
                "error_code": constants.ERR_ILLEGAL_OPERATION,
                "error_message": "I only do reads, really",
            },
        )

    def testHandleUnexpectedAck(self):
        self.handler._last_block_sent = 1
        self.handler._reset_timeout = Mock()
        self.handler._next_block = Mock()
        self.handler._handle_ack(2)
        self.handler._reset_timeout.assert_not_called()

    def testHandleTimeout(self):
        self.handler._retries = 3
        self.handler._retransmits = 2
        self.handler._transmit_data = Mock()
        self.handler._handle_timeout()
        self.assertEqual(self.handler._retransmits, 3)
        self.handler._transmit_data.assert_called_with()
        self.assertEqual(self.handler._stats.error, {})

        self.handler._retries = 1
        self.handler._retransmits = 2
        self.handler._handle_timeout()
        self.assertEqual(
            self.handler._stats.error,
            {
                "error_code": constants.ERR_UNDEFINED,
                "error_message": "timeout after 2 retransmits.",
            },
        )
        self.assertTrue(self.handler._should_stop)

    def testNextBlock(self):
        class MockResponse:
            def __init__(self, dataiter):
                self._dataiter = dataiter

            def read(self, size=0):
                try:
                    return next(self._dataiter)
                except StopIteration:
                    return None

        # single-packet file
        self.handler._last_block_sent = 0
        self.handler._block_size = 1400
        self.handler._response_data = StringResponseData("bacon")
        self.handler._next_block()
        self.assertEqual(self.handler._current_block, b"bacon")
        self.assertEqual(self.handler._last_block_sent, 1)

        # multi-packet file
        self.handler._last_block_sent = 0
        self.handler._block_size = 1400
        self.handler._response_data = StringResponseData("bacon" * 281)
        self.handler._next_block()
        self.assertEqual(self.handler._current_block, b"bacon" * 280)
        self.assertEqual(self.handler._last_block_sent, 1)
        self.handler._next_block()
        self.assertEqual(self.handler._current_block, b"bacon")
        self.assertEqual(self.handler._last_block_sent, 2)

        # partial read
        data = MockResponse(iter("bacon"))
        self.handler._last_block_sent = 0
        self.handler._block_size = 1400
        self.handler._response_data.read = data.read
        self.handler._next_block()
        self.assertEqual(self.handler._current_block, "bacon")
        self.assertEqual(self.handler._last_block_sent, 1)

        self.handler._last_block_sent = constants.MAX_BLOCK_NUMBER + 1
        self.handler._next_block()
        self.assertEqual(self.handler._last_block_sent, 0)

        self.handler._response_data.read = Mock(side_effect=Exception("boom!"))
        self.handler._next_block()
        self.assertEqual(
            self.handler._stats.error,
            {
                "error_code": constants.ERR_UNDEFINED,
                "error_message": "Error while reading from source",
            },
        )
        self.assertTrue(self.handler._should_stop)

    def testTransmitData(self):
        # we have tested sending data so here we should just test the edge case
        # where there is no more data to send
        self.handler._current_block = b""
        self.handler._transmit_data()
        self.handler._handle_ack(0)
        self.assertTrue(self.handler._should_stop)

    def testTransmitOACK(self):
        self.handler._options = {"opt1": "value1"}
        self.handler._get_listener().sendto = Mock()
        self.handler._stats.packets_sent = 1
        self.handler._transmit_oack()
        self.assertEqual(self.handler._stats.packets_sent, 2)
        self.handler._get_listener().sendto.assert_called_with(
            # OACK code == 6
            b"\x00\x06opt1\x00value1\x00",
            ("127.0.0.1", 5678),
        )
