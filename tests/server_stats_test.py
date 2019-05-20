#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import collections
import time
import unittest
import threading
from unittest.mock import patch

from fbtftp.base_server import ServerStats


class testServerStats(unittest.TestCase):
    @patch("threading.Lock")
    def setUp(self, mock):
        self.st = ServerStats(server_addr="127.0.0.1", interval=2)
        self.start_time = time.time()
        self.assertEqual(self.st.server_addr, "127.0.0.1")
        self.assertEqual(self.st.interval, 2)
        self.assertLessEqual(self.st.start_time, self.start_time)
        self.assertIsInstance(self.st._counters, collections.Counter)
        self.assertIsInstance(self.st._counters_lock, type(threading.Lock()))
        self.st._counters_lock = mock()

    def testSetGetCounters(self):
        self.st.set_counter("testcounter", 100)
        self.assertEqual(self.st.get_counter("testcounter"), 100)
        self.assertEqual(self.st._counters_lock.__enter__.call_count, 1)
        self.assertEqual(self.st._counters_lock.__exit__.call_count, 1)

    def testIncrementCounter(self):
        self.st.set_counter("testcounter", 100)
        self.st.increment_counter("testcounter")
        self.assertEqual(self.st.get_counter("testcounter"), 101)
        self.assertEqual(self.st._counters_lock.__enter__.call_count, 2)
        self.assertEqual(self.st._counters_lock.__exit__.call_count, 2)

    def testResetCounter(self):
        self.st.set_counter("testcounter", 100)
        self.assertEqual(self.st.get_counter("testcounter"), 100)
        self.st.reset_counter("testcounter")
        self.assertEqual(self.st.get_counter("testcounter"), 0)
        self.assertEqual(self.st._counters_lock.__enter__.call_count, 2)
        self.assertEqual(self.st._counters_lock.__exit__.call_count, 2)

    def testGetAndResetCounter(self):
        self.st.set_counter("testcounter", 100)
        self.assertEqual(self.st.get_and_reset_counter("testcounter"), 100)
        self.assertEqual(self.st.get_counter("testcounter"), 0)
        self.assertEqual(self.st._counters_lock.__enter__.call_count, 2)
        self.assertEqual(self.st._counters_lock.__exit__.call_count, 2)

    def testGetAllCounters(self):
        self.st.set_counter("testcounter1", 100)
        self.st.set_counter("testcounter2", 200)
        counters = self.st.get_all_counters()
        self.assertEqual(len(counters), 2)
        self.assertEqual(self.st._counters_lock.__enter__.call_count, 3)
        self.assertEqual(self.st._counters_lock.__exit__.call_count, 3)

    def testGetAndResetAllCounters(self):
        self.st.set_counter("testcounter1", 100)
        self.st.set_counter("testcounter2", 200)
        counters = self.st.get_and_reset_all_counters()
        self.assertEqual(len(counters), 2)
        self.assertEqual(counters["testcounter1"], 100)
        self.assertEqual(counters["testcounter2"], 200)
        self.assertEqual(self.st._counters_lock.__enter__.call_count, 3)
        self.assertEqual(self.st._counters_lock.__exit__.call_count, 3)

    def testResetAllCounters(self):
        self.st.set_counter("testcounter1", 100)
        self.st.set_counter("testcounter2", 200)
        self.st.reset_all_counters()
        self.assertEqual(self.st.get_counter("testcounter1"), 0)
        self.assertEqual(self.st.get_counter("testcounter2"), 0)
        self.assertEqual(self.st._counters_lock.__enter__.call_count, 3)
        self.assertEqual(self.st._counters_lock.__exit__.call_count, 3)

    def testDuration(self):
        self.assertGreater(self.st.duration(), 0)
