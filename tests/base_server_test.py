#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest.mock import patch, Mock
import unittest

from fbtftp.base_server import BaseServer

MOCK_SOCKET_FILENO = 100
SELECT_EPOLLIN = 1


class MockSocketListener:
    def __init__(self, network_queue):
        self._network_queue = network_queue

    def recvfrom(self, blocksize):
        data = self._network_queue.pop(0)
        peer = "::1"  # assuming v6, but this is invariant for this test
        return data, peer

    def fileno(self):
        # just a given socket fileno that will have to be matched by
        # testBaseServer.poll_mock below. This is to trick the
        # BaseServer.run_once()'s' select.epoll.poll() method...
        return MOCK_SOCKET_FILENO

    def close(self):
        pass


class StaticServer(BaseServer):
    def __init__(
        self,
        address,
        port,
        retries,
        timeout,
        root,
        stats_callback,
        stats_interval,
        network_queue,
    ):
        super().__init__(
            address, port, retries, timeout, stats_callback, stats_interval
        )
        self._root = root
        # mock the network
        self._listener = MockSocketListener(network_queue)
        self._handler = None

    def get_handler(self, addr, peer, path, options):
        """ returns a mock handler """
        self._handler = Mock(addr, peer, path, options)
        self._handler.addr = addr
        self._handler.peer = peer
        self._handler.path = path
        self._handler.options = options
        self._handler.start = Mock()
        return self._handler


class testBaseServer(unittest.TestCase):
    def setUp(self):
        self.host = "::"  # assuming v6, but this is invariant for this test
        self.port = 0  # let the kernel choose
        self.timeout = 100
        self.retries = 200
        self.interval = 1
        self.network_queue = []

    def poll_mock(self):
        """
        mock the select.epoll.poll() method, returns an iterable containing a
        list of (fileno, eventmask), the fileno constant matches the
        MockSocketListener.fileno() method, eventmask matches select.EPOLLIN
        """
        if len(self.network_queue) > 0:
            return [(MOCK_SOCKET_FILENO, SELECT_EPOLLIN)]
        return []

    def prepare_and_run(self, network_queue):
        server = StaticServer(
            self.host,
            self.port,
            self.retries,
            self.timeout,
            None,
            Mock(),
            self.interval,
            self.network_queue,
        )
        server._server_stats.increment_counter = Mock()
        server.run(run_once=True)
        server.close()
        self.assertTrue(server._should_stop)
        self.assertTrue(server._handler.daemon)
        server._handler.start.assert_called_with()
        self.assertEqual(server._handler.addr, ("::", 0))
        self.assertEqual(server._handler.peer, "::1")
        server._server_stats.increment_counter.assert_called_with("process_count")
        return server._handler

    @patch("select.epoll")
    def testRRQ(self, epoll_mock):
        # link the self.poll_mock() method with the select.epoll patched object
        epoll_mock.return_value.poll.side_effect = self.poll_mock
        self.network_queue = [
            # RRQ + file name + mode + optname + optvalue
            b"\x00\x01some_file\x00binascii\x00opt1_key\x00opt1_val\x00"
        ]
        handler = self.prepare_and_run(self.network_queue)

        self.assertEqual(handler.path, "some_file")
        self.assertEqual(
            handler.options,
            {
                "default_timeout": 100,
                "mode": "binascii",
                "opt1_key": "opt1_val",
                "retries": 200,
            },
        )

    def start_timer_and_wait_for_callback(self, stats_callback):
        server = StaticServer(
            self.host,
            self.port,
            self.retries,
            self.timeout,
            None,
            stats_callback,
            self.interval,
            [],
        )
        server.restart_stats_timer(run_once=True)
        # wait for the stats callback to be executed
        for _ in range(10):
            import time

            time.sleep(1)
            if stats_callback.mock_called:
                print("Stats callback executed")
                break
        server._metrics_timer.cancel()

    def testTimer(self):
        stats_callback = Mock()
        self.start_timer_and_wait_for_callback(stats_callback)

    def testTimerNoCallBack(self):
        stats_callback = None
        server = StaticServer(
            self.host,
            self.port,
            self.retries,
            self.timeout,
            None,
            stats_callback,
            self.interval,
            [],
        )
        ret = server.restart_stats_timer(run_once=True)
        self.assertIsNone(ret)

    def testCallbackException(self):
        stats_callback = Mock()
        stats_callback.side_effect = Exception("boom!")
        self.start_timer_and_wait_for_callback(stats_callback)

    @patch("select.epoll")
    def testUnexpectedOpsCode(self, epoll_mock):
        # link the self.poll_mock() emthod with the select.epoll patched object
        epoll_mock.return_value.poll.side_effect = self.poll_mock
        self.network_queue = [
            # RRQ + file name + mode + optname + optvalue
            b"\x00\xffsome_file\x00binascii\x00opt1_key\x00opt1_val\x00"
        ]
        server = StaticServer(
            self.host,
            self.port,
            self.retries,
            self.timeout,
            None,
            Mock(),
            self.interval,
            self.network_queue,
        )
        server.run(run_once=True)
        self.assertIsNone(server._handler)
