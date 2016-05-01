#!/usr/bin/env python3
# Copyright (c) 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import socket
from unittest.mock import patch, Mock
import unittest

from fbtftp.base_server import BaseServer

MOCK_SOCKET_FILENO = 100
SELECT_EPOLLIN = 1


class MockSocketListener:
    def __init__(self, network_queue, v4=False):
        self._network_queue = network_queue
        self._peer = '127.0.0.2' if v4 else '::1'

    def recvfrom(self, blocksize):
        data = self._network_queue.pop(0)
        return data, self._peer

    def fileno(self):
        # just a given socket fileno that will have to be matched by
        # testBaseServer.poll_mock below. This is to trick the
        # BaseServer.run_once()'s' select.epoll.poll() method...
        return MOCK_SOCKET_FILENO

    def close(self):
        pass


class StaticServer(BaseServer):
    def __init__(
        self, address, port, retries, timeout, root, stats_callback,
        stats_interval, network_queue
    ):
        super().__init__(
            address, port, retries, timeout, stats_callback, stats_interval
        )
        self._root = root
        self._listener = MockSocketListener(
            network_queue, self._listener.family == socket.AF_INET)
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

    V4HOST = '127.0.0.1'
    V6HOST = '::'

    def setUp(self):
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

    def get_server_v4(self):
        return StaticServer(
            self.V4HOST, self.port, self.retries, self.timeout, None, Mock(),
            self.interval, self.network_queue
        )

    def get_server_v6(self):
        return StaticServer(
            self.V6HOST, self.port, self.retries, self.timeout, None, Mock(),
            self.interval, self.network_queue
        )

    def prepare_and_run_server_v6(self):
        handler = self.prepare_and_run_server(self.get_server_v6())
        self.assertEqual(handler.addr, (self.V6HOST, 0))
        self.assertEqual(handler.peer, '::1')
        return handler

    def prepare_and_run_server_v4(self):
        handler = self.prepare_and_run_server(self.get_server_v4())
        self.assertEqual(handler.addr, (self.V4HOST, 0))
        self.assertEqual(handler.peer, '127.0.0.2')
        return handler

    def prepare_and_run_server(self, server):
        server._server_stats.increment_counter = Mock()
        server.run(run_once=True)
        server.close()
        self.assertTrue(server._should_stop)
        self.assertTrue(server._handler.daemon)
        server._handler.start.assert_called_with()
        server._server_stats.increment_counter.assert_called_with(
            'process_count'
        )
        return server._handler

    @patch('select.epoll')
    def testRRQ(self, epoll_mock):
        # link the self.poll_mock() method with the select.epoll patched object
        epoll_mock.return_value.poll.side_effect = self.poll_mock
        # RRQ + file name + mode + optname + optvalue
        payload = b'\x00\x01some_file\x00binascii\x00opt1_key\x00opt1_val\x00'
        self.network_queue.append(payload)
        handler_v6 = self.prepare_and_run_server_v6()
        self.network_queue.append(payload)
        handler_v4 = self.prepare_and_run_server_v4()
        for handler in [handler_v4, handler_v6]:
            self.assertEqual(handler.path, 'some_file')
            self.assertEqual(
                handler.options, {
                    'default_timeout': 100,
                    'mode': 'binascii',
                    'opt1_key': 'opt1_val',
                    'retries': 200
                }
            )

    def start_timer_and_wait_for_callback(self, stats_callback):
        for server in [self.get_server_v4(), self.get_server_v6()]:
            server.restart_stats_timer(run_once=True)
            # wait for the stats callback to be executed
            for i in range(10):
                import time
                time.sleep(1)
                if stats_callback.mock_called:
                    print('Stats callback executed')
                    break
            server._metrics_timer.cancel()

    def testTimer(self):
        stats_callback = Mock()
        self.start_timer_and_wait_for_callback(stats_callback)

    def testTimerNoCallBack(self):
        for server in [self.get_server_v4(), self.get_server_v6()]:
            ret = server.restart_stats_timer(run_once=True)
            self.assertIsNone(ret)

    def testCallbackException(self):
        stats_callback = Mock()
        stats_callback.side_effect = Exception('boom!')
        self.start_timer_and_wait_for_callback(stats_callback)

    @patch('select.epoll')
    def testUnexpectedOpsCode(self, epoll_mock):
        # link the self.poll_mock() emthod with the select.epoll patched object
        epoll_mock.return_value.poll.side_effect = self.poll_mock
        # RRQ + file name + mode + optname + optvalue
        payload = b'\x00\xffsome_file\x00binascii\x00opt1_key\x00opt1_val\x00'
        for server in [self.get_server_v4(), self.get_server_v6()]:
            self.network_queue.append(payload)
            server.run(run_once=True)
            self.assertIsNone(server._handler)
