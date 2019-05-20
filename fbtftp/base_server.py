#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import collections
import ipaddress
import logging
import select
import socket
import struct
import threading
import time
import traceback

from . import constants


class ServerStats:
    def __init__(self, server_addr=None, interval=None):
        """
        `ServerStats` represents a digest of what happened during the server's
        lifetime.

        This class exposes a counter interface with get/set/reset methods and
        an atomic get-and-reset.

        An instance of this class is passed to a periodic function that is
        executed by a background thread inside the `BaseServer` object.
        See `stats_callback` in the `BaseServer` constructor.

        If you use it in a metric publishing callback, remember to use atomic
        operations and to reset the counters to have a fresh start. E.g. see
        `get_and_reset_all_counters'.

        Args:
            server_addr (str): the server address, either v4 or v6.
            interval (int): stats interval in seconds.

        Note:
            `server_addr` and `interval` are provided by the `BaseServer`
            class.  They are not used in this class, they are there for the
            programmer's convenience, in case one wants to use them.
        """
        self.server_addr = server_addr
        self.interval = interval
        self.start_time = time.time()
        self._counters = collections.Counter()
        self._counters_lock = threading.Lock()

    def get_all_counters(self):
        """
        Return all counters as a dictionary. This operation is atomic.

        Returns:
            dict: all the counters.
        """
        with self._counters_lock:
            return dict(self._counters)

    def get_and_reset_all_counters(self):
        """
        Return all counters as a dictionary and reset them.
        This operation is atomic.

        Returns:
            dict: all the counters
        """
        with self._counters_lock:
            counters = dict(self._counters)
            self._counters.clear()
        return counters

    def get_counter(self, name):
        """
        Get a counter value by name. Do not use this method if you have to
        reset a counter after getting it. Use `get_and_reset_counter` instead.

        Args:
            name (str): the counter

        Returns:
            int: the value of the counter
        """
        return self._counters[name]

    def set_counter(self, name, value):
        """
        Set a counter value by name, atomically.

        Args:
            name (str): counter's name
            value (str): counter's value
        """
        with self._counters_lock:
            self._counters[name] = value

    def increment_counter(self, name, increment=1):
        """
        Increment a counter value by name, atomically. The increment can be
        negative.

        Args:
            name (str): the counter's name
            increment (int): the increment step, defaults to 1.
        """
        with self._counters_lock:
            self._counters[name] += increment

    def reset_counter(self, name):
        """
        Reset counter atomically.

        Args:
            name (str): counter's name
        """
        with self._counters_lock:
            self._counters[name] = 0

    def get_and_reset_counter(self, name):
        """
        Get and reset a counter value by name atomically.

        Args:
            name (str): counter's name

        Returns:
            : counter's value
        """
        with self._counters_lock:
            value = self._counters[name]
            self._counters[name] = 0
            return value

    def reset_all_counters(self):
        """
        Reset all the counters atomically.
        """
        with self._counters_lock:
            self._counters.clear()

    def duration(self):
        """
        Return the server uptime using naive timestamps.

        Returns:
            float: uptime in seconds.
        """
        return time.time() - self.start_time


class BaseServer:
    def __init__(
        self,
        address,
        port,
        retries,
        timeout,
        server_stats_callback=None,
        stats_interval_seconds=constants.DATAPOINTS_INTERVAL_SECONDS,
    ):
        """
        This base class implements the process which deals with accepting new
        requests.


        Note:
            This class doesn't have to be used directly, you must inherit from
            it and override the `get_handler()`` method to return an instance
            of `BaseHandler`.

        Args:
            address (str): address (IPv4 or IPv6) the server needs to bind to.

            port (int): the port the server needs to bind to.

            retries (int): number of retries, how many times the server has to
                retry sending a datagram before it will interrupt the
                communication. This is passed to the `BaseHandler` class.

            timeout (int): time in seconds, this is passed to the `BaseHandler`
                class. It used in two ways:
                    - as timeout in `socket.socket.recvfrom()`.
                    - as maximum time to expect an ACK from a client.

            server_stats_callback (callable): a callable, this gets called
                periodically by a background thread. The callable must accept
                one argument which is an instance of the `ServerStats` class.
                The statistics callback is not re-entrant, if you need this you
                have to implement your own locking logic.

            stats_interval_seconds (int): how often, in seconds,
                `server_stats_callback` will be executed.
        """
        self._address = address
        self._port = port
        self._retries = retries
        self._timeout = timeout
        self._server_stats_callback = server_stats_callback
        # the format of the peer tuple is different for v4 and v6
        self._family = socket.AF_INET6
        if isinstance(ipaddress.ip_address(self._address), ipaddress.IPv4Address):
            self._family = socket.AF_INET
        self._listener = socket.socket(self._family, socket.SOCK_DGRAM)
        self._listener.setblocking(0)  # non-blocking
        self._listener.bind((address, port))
        self._epoll = select.epoll()
        self._epoll.register(self._listener.fileno(), select.EPOLLIN)
        self._should_stop = False
        self._server_stats = ServerStats(address, stats_interval_seconds)
        self._metrics_timer = None

    def run(self, run_once=False):
        """
        Run the infinite serving loop.

        Args:
            run_once (bool): If True it will exit the loop after first
                iteration.  Note this is only used in unit tests.
        """
        # First start of the server stats thread
        self.restart_stats_timer(run_once)

        while not self._should_stop:
            self.run_once()
            if run_once:
                break
        self._epoll.close()
        self._listener.close()
        if self._metrics_timer is not None:
            self._metrics_timer.cancel()

    def _metrics_callback_wrapper(self, run_once=False):
        """
        Runs the callback, catches and logs exceptions, reschedules a new run
        for the callback, only if run_once is False (this is used only in unit
        tests).
        """
        logging.debug("Running the metrics callback")
        try:
            self._server_stats_callback(self._server_stats)
        except Exception as exc:
            logging.exception(str(exc))
        if not run_once:
            self.restart_stats_timer()

    def restart_stats_timer(self, run_once=False):
        """
        Start metric pushing timer thread, if a callback was specified.
        """
        if self._server_stats_callback is None:
            logging.warning(
                "No callback specified for server statistics "
                "logging, will continue without"
            )
            return
        self._metrics_timer = threading.Timer(
            self._server_stats.interval, self._metrics_callback_wrapper, [run_once]
        )
        logging.debug(
            "Starting the metrics callback in {sec}s".format(
                sec=self._server_stats.interval
            )
        )
        self._metrics_timer.start()

    def run_once(self):
        """
        Uses edge polling object (`socket.epoll`) as an event notification
        facility to know when data is ready to be retrived from the listening
        socket. See http://linux.die.net/man/4/epoll .
        """
        events = self._epoll.poll()
        for fileno, eventmask in events:
            if not eventmask & select.EPOLLIN:
                continue
            if fileno == self._listener.fileno():
                self.on_new_data()
                continue

    def on_new_data(self):
        """
        Deals with incoming RRQ packets. This is called by `run_once` when data
        is available on the listening socket.
        This method deals with extracting all the relevant information from the
        request (like file, transfer mode, path, and options).
        If all is good it will run the `get_handler` method, which returns a
        `BaseHandler` object. `BaseHandler` is a subclass of a
        `multiprocessing.Process` class so calling `start()` on it will cause
        a `fork()`.
        """
        data, peer = self._listener.recvfrom(constants.DEFAULT_BLKSIZE)
        code = struct.unpack("!H", data[:2])[0]
        if code != constants.OPCODE_RRQ:
            logging.warning(
                "unexpected TFTP opcode %d, expected %d" % (code, constants.OPCODE_RRQ)
            )
            return

        # extract options
        tokens = list(filter(bool, data[2:].decode("latin-1").split("\x00")))
        if len(tokens) < 2 or len(tokens) % 2 != 0:
            logging.error(
                "Received malformed packet, ignoring "
                "(tokens length: {tl})".format(tl=len(tokens))
            )
            return

        path = tokens[0]
        options = collections.OrderedDict(
            [
                ("mode", tokens[1].lower()),
                ("default_timeout", self._timeout),
                ("retries", self._retries),
            ]
        )
        pos = 2
        while pos < len(tokens):
            options[tokens[pos].lower()] = tokens[pos + 1]
            pos += 2

        # fork a child process
        try:
            proc = self.get_handler((self._address, self._port), peer, path, options)
            if proc is None:
                logging.warning(
                    "The handler is null! Not serving the request from %s", peer
                )
                return
            proc.daemon = True
            proc.start()
        except Exception as e:
            logging.error(
                "creating a handler for %r raised an exception %s" % (path, e)
            )
            logging.error(traceback.format_exc())

        # Increment number of spawned TFTP workers in stats time frame
        self._server_stats.increment_counter("process_count")

    def get_handler(self, server_addr, peer, path, options):
        """
        Returns an instance of `BaseHandler`.

        Note:
            This is a virtual method and must be overridden in a sub-class.
            This method must return an instance of `BaseHandler`.

        Args:
            server_addr (tuple): tuple containing ip of the server and
                listening port.

            peer (tuple): tuple containing ip and port of the client.

            path (string): the file path requested by the client

            options (dict): a dictionary containing the options the clients
                wants to negotiate.

        Example of options:
            - mode (string): can be netascii or octet. See RFC 1350.
            - retries (int)
            - timeout (int)
            - tsize (int): transfer size option. See RFC 1784.
            - blksize: size of blocks. See RFC 1783 and RFC 2349.
        """
        raise NotImplementedError()

    def close(self):
        """
        Stops the server, by setting a boolean flag which will be picked by
        the main while loop.
        """
        self._should_stop = True
