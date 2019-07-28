#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from collections import OrderedDict
import io
import ipaddress
import logging
import multiprocessing
import socket
import struct
import sys
import time

from . import constants
from .netascii import NetasciiReader


class ResponseData:
    """A base class representing a file-like object"""

    def read(self, n):
        raise NotImplementedError()

    def size(self):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()


class StringResponseData(ResponseData):
    """
    A convenience subclass of `ResponseData` that transforms an input String
    into a file-like object.
    """

    def __init__(self, string):
        self._size = len(string.encode("latin-1"))
        self._reader = io.StringIO(string)

    def read(self, n):
        return bytes(self._reader.read(n).encode("latin-1"))

    def size(self):
        return self._size

    def close(self):
        pass


class SessionStats:
    """
    SessionStats represents a digest of what happened during a session.
    Data inside the object gets populated at the end of a session.
    See `__init__` to see what you'll get.

    Note:
        You should never need to instantiate an object of this class.
        This object is what gets passed to the callback you provide to the
        `BaseHandler` class.
    """

    def __init__(self, server_addr, peer, file_path):
        self.peer = peer
        self.server_addr = server_addr
        self.file_path = file_path
        self.error = {}
        self.options = {}
        self.start_time = time.time()
        self.packets_sent = 0
        self.packets_acked = 0
        self.bytes_sent = 0
        self.retransmits = 0
        self.blksize = constants.DEFAULT_BLKSIZE

    def duration(self):
        return time.time() - self.start_time


class BaseHandler(multiprocessing.Process):
    def __init__(self, server_addr, peer, path, options, stats_callback):
        """
        Class that deals with talking to a single client. Being a subclass of
        `multiprocessing.Process` this will run in a separate process from the
        main process.

        Note:
            Do not use this class as is, inherit from it and override the
            `get_response_data` method which must return a subclass of
            `ResponseData`.

        Args:
            server_addr (tuple): (ip, port) of the server

            peer (tuple): (ip, port of) the peer

            path (string): requested file

            options (dict): a dictionary containing the options the client
                wants to negotiate.

            stats_callback (callable): a callable that will be executed at the
                end of the session. It gets passed an instance of the
                `SessionStats` class.
        """
        self._timeout = int(options["default_timeout"])
        self._server_addr = server_addr
        self._reset_timeout()
        self._retries = int(options["retries"])
        self._block_size = constants.DEFAULT_BLKSIZE
        self._last_block_sent = 0
        self._retransmits = 0
        self._global_retransmits = 0
        self._current_block = None
        self._should_stop = False
        self._waiting_last_ack = False
        self._path = path
        self._options = options
        self._stats_callback = stats_callback
        self._response_data = None
        self._listener = None

        self._peer = peer
        logging.info(
            "New connection from peer `%s` asking for path `%s`"
            % (str(peer), str(path))
        )
        self._family = socket.AF_INET6
        # the format of the peer tuple is different for v4 and v6
        if isinstance(ipaddress.ip_address(server_addr[0]), ipaddress.IPv4Address):
            self._family = socket.AF_INET
            # peer address format is different in v4 world
            self._peer = (self._peer[0].replace("::ffff:", ""), self._peer[1])

        self._stats = SessionStats(self._server_addr, self._peer, self._path)

        try:
            self._response_data = self.get_response_data()
        except FileNotFoundError as e:
            logging.warning(str(e))
            self._stats.error = {
                "error_code": constants.ERR_FILE_NOT_FOUND,
                "error_message": str(e),
            }
        except Exception as e:
            logging.exception("Caught exception: %s." % e)
            self._stats.error = {
                "error_code": constants.ERR_UNDEFINED,
                "error_message": str(e),
            }

        super().__init__()

    def _get_listener(self):
        if not self._listener:
            self._listener = socket.socket(self._family, socket.SOCK_DGRAM)
            self._listener.bind((str(self._server_addr[0]), 0))
        return self._listener

    def _on_close(self):
        """
        Called at the end of a session.

        This method sets number of retransmissions and calls the stats callback
        at the end of the session.
        """
        self._stats.retransmits = self._global_retransmits
        self._stats_callback(self._stats)

    def _close(self, test=False):
        """
        Wrapper around `_on_close`. Its duty is to perform the necessary
        cleanup. Closing `ResponseData` object, closing UDP sockets, and
        gracefully exiting the process with exit code of 0.
        """
        try:
            self._on_close()
        except Exception as e:
            logging.exception("Exception raised when calling _on_close: %s" % e)
        finally:
            logging.debug("Closing response data object")
            if self._response_data:
                self._response_data.close()
            logging.debug("Closing socket")
            self._get_listener().close()
            logging.debug("Dying.")
            if test is False:
                sys.exit(0)

    def _parse_options(self):
        """
        Method that deals with parsing/validation options provided by the
        client.
        """
        opts_to_ack = OrderedDict()
        # We remove retries and default_timeout from self._options because
        # we don't need to include them in the OACK response to the client.
        # Their value is already hold in self._retries and self._timeout.
        del self._options["retries"]
        del self._options["default_timeout"]
        logging.info(
            "Options requested from peer {}:  {}".format(self._peer, self._options)
        )
        self._stats.options_in = self._options
        if "mode" in self._options and self._options["mode"] == "netascii":
            self._response_data = NetasciiReader(self._response_data)
        elif "mode" in self._options and self._options["mode"] != "octet":
            self._stats.error = {
                "error_code": constants.ERR_ILLEGAL_OPERATION,
                "error_message": "Unknown mode: %r" % self._options["mode"],
            }
            self._transmit_error()
            self._close()
            return  # no way anything else will succeed now
        # Let's ack the options in the same order we got asked for them
        # The RFC mentions that option order is not significant, but it can't
        # hurt. This relies on Python 3.6 dicts to be ordered.
        for k, v in self._options.items():
            if k == "blksize":
                opts_to_ack["blksize"] = v
                self._block_size = int(v)
            if k == "tsize":
                self._tsize = self._response_data.size()
                if self._tsize is not None:
                    opts_to_ack["tsize"] = str(self._tsize)
            if k == "timeout":
                opts_to_ack["timeout"] = v
                self._timeout = int(v)

        self._options = opts_to_ack  # only ACK options we can handle
        logging.info(
            "Options to ack for peer {}:  {}".format(self._peer, self._options)
        )
        self._stats.blksize = self._block_size
        self._stats.options = self._options
        self._stats.options_acked = self._options

    def run(self):
        """This is the main serving loop."""
        if self._stats.error:
            self._transmit_error()
            self._close()
            return
        self._parse_options()
        if self._options:
            self._transmit_oack()
        else:
            self._next_block()
            self._transmit_data()
        while not self._should_stop:
            try:
                self.run_once()
            except (KeyboardInterrupt, SystemExit):
                logging.info(
                    "Caught KeyboardInterrupt/SystemExit exception. " "Will exit."
                )
                break
        self._close()

    def run_once(self):
        """The main body of the server loop."""
        self.on_new_data()
        if time.time() > self._expire_ts:
            self._handle_timeout()

    def _reset_timeout(self):
        """
        This method resets the connection timeout in order to extend its
        lifetime..
        It does so setting the timestamp in the future.
        """
        self._expire_ts = time.time() + self._timeout

    def on_new_data(self):
        """
        Called when new data is available on the socket.

        This method will extract acknowledged block numbers and handle
        possible errors.
        """
        # Note that we use blocking socket, because it has its own dedicated
        # process. We read only 512 bytes.
        try:
            listener = self._get_listener()
            listener.settimeout(self._timeout)
            data, peer = listener.recvfrom(constants.DEFAULT_BLKSIZE)
            listener.settimeout(None)
        except socket.timeout:
            return
        if peer != self._peer:
            logging.error("Unexpected peer: %s, expected %s" % (peer, self._peer))
            self._should_stop = True
            return
        code, block_number = struct.unpack("!HH", data[:4])
        if code == constants.OPCODE_ERROR:
            # When the client sends an OPCODE_ERROR#
            # the block number is the ERR codes in constants.py
            self._stats.error = {
                "error_code": block_number,
                "error_message": data[4:-1].decode("ascii", "ignore"),
            }
            # An error was reported by the client which terminates the exchange
            logging.error(
                "Error reported from client: %s" % self._stats.error["error_message"]
            )
            self._transmit_error()
            self._should_stop = True
            return
        if code != constants.OPCODE_ACK:
            logging.error(
                "Expected an ACK opcode from %s, got: %d" % (self._peer, code)
            )
            self._stats.error = {
                "error_code": constants.ERR_ILLEGAL_OPERATION,
                "error_message": "I only do reads, really",
            }
            self._transmit_error()
            self._should_stop = True
            return
        self._handle_ack(block_number)

    def _handle_ack(self, block_number):
        """Deals with a client ACK packet."""

        if block_number != self._last_block_sent:
            # Unexpected ACK, let's ignore this.
            return
        self._reset_timeout()
        self._retransmits = 0
        self._stats.packets_acked += 1
        if self._waiting_last_ack:
            self._should_stop = True
            return
        self._next_block()
        self._transmit_data()

    def _handle_timeout(self):
        if self._retries >= self._retransmits:
            self._transmit_data()
            self._retransmits += 1
            self._global_retransmits += 1
            return

        error_msg = "timeout after {} retransmits.".format(self._retransmits)
        if self._waiting_last_ack:
            error_msg += " Missed last ack."

        self._stats.error = {
            "error_code": constants.ERR_UNDEFINED,
            "error_message": error_msg,
        }
        self._should_stop = True
        logging.error(self._stats.error["error_message"])

    def _next_block(self):
        """
        Reads the next block from `ResponseData`. If there are problems
        reading from it, an error will be reported to the client"
        """
        self._last_block_sent += 1
        if self._last_block_sent > constants.MAX_BLOCK_NUMBER:
            self._last_block_sent = 0  # Wrap around the block counter.
        try:
            last_size = 0  # current_block size before read. Used to check EOF.
            self._current_block = self._response_data.read(self._block_size)
            while (
                len(self._current_block) != self._block_size
                and len(self._current_block) != last_size
            ):
                last_size = len(self._current_block)
                self._current_block += self._response_data.read(
                    self._block_size - last_size
                )
        except Exception as e:
            logging.exception("Error while reading from source: %s" % e)
            self._stats.error = {
                "error_code": constants.ERR_UNDEFINED,
                "error_message": "Error while reading from source",
            }
            self._transmit_error()
            self._should_stop = True

    def _transmit_data(self):
        """Method that deals with sending a block to the wire."""

        if self._current_block is None:
            self._transmit_oack()
            return

        fmt = "!HH%ds" % len(self._current_block)
        packet = struct.pack(
            fmt, constants.OPCODE_DATA, self._last_block_sent, self._current_block
        )
        self._get_listener().sendto(packet, self._peer)
        self._stats.packets_sent += 1
        self._stats.bytes_sent += len(self._current_block)
        if len(self._current_block) < self._block_size:
            self._waiting_last_ack = True

    def _transmit_oack(self):
        """Method that deals with sending OACK datagrams on the wire."""
        opts = []
        for key, val in self._options.items():
            fmt = str("%dsx%ds" % (len(key), len(val)))
            opts.append(
                struct.pack(
                    fmt, bytes(key.encode("latin-1")), bytes(val.encode("latin-1"))
                )
            )
        opts.append(b"")
        fmt = str("!H")
        packet = struct.pack(fmt, constants.OPCODE_OACK) + b"\x00".join(opts)
        self._get_listener().sendto(packet, self._peer)
        self._stats.packets_sent += 1

    def _transmit_error(self):
        """Transmits an error to the client and terminates the exchange."""
        fmt = str(
            "!HH%dsx" % (len(self._stats.error["error_message"].encode("latin-1")))
        )
        packet = struct.pack(
            fmt,
            constants.OPCODE_ERROR,
            self._stats.error["error_code"],
            bytes(self._stats.error["error_message"].encode("latin-1")),
        )
        self._get_listener().sendto(packet, self._peer)

    def get_response_data(self):
        """
        This method has to be overridden and must return an object of type
        `ResponseData`.
        """
        raise NotImplementedError()
