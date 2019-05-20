#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import logging
import os

from fbtftp.base_handler import BaseHandler
from fbtftp.base_handler import ResponseData
from fbtftp.base_server import BaseServer


class FileResponseData(ResponseData):
    def __init__(self, path):
        self._size = os.stat(path).st_size
        self._reader = open(path, "rb")

    def read(self, n):
        return self._reader.read(n)

    def size(self):
        return self._size

    def close(self):
        self._reader.close()


def print_session_stats(stats):
    logging.info("Stats: for %r requesting %r" % (stats.peer, stats.file_path))
    logging.info("Error: %r" % stats.error)
    logging.info("Time spent: %dms" % (stats.duration() * 1e3))
    logging.info("Packets sent: %d" % stats.packets_sent)
    logging.info("Packets ACKed: %d" % stats.packets_acked)
    logging.info("Bytes sent: %d" % stats.bytes_sent)
    logging.info("Options: %r" % stats.options)
    logging.info("Blksize: %r" % stats.blksize)
    logging.info("Retransmits: %d" % stats.retransmits)
    logging.info("Server port: %d" % stats.server_addr[1])
    logging.info("Client port: %d" % stats.peer[1])


def print_server_stats(stats):
    """
    Print server stats - see the ServerStats class
    """
    # NOTE: remember to reset the counters you use, to allow the next cycle to
    #       start fresh
    counters = stats.get_and_reset_all_counters()
    logging.info("Server stats - every %d seconds" % stats.interval)
    if "process_count" in counters:
        logging.info(
            "Number of spawned TFTP workers in stats time frame : %d"
            % counters["process_count"]
        )


class StaticHandler(BaseHandler):
    def __init__(self, server_addr, peer, path, options, root, stats_callback):
        self._root = root
        super().__init__(server_addr, peer, path, options, stats_callback)

    def get_response_data(self):
        return FileResponseData(os.path.join(self._root, self._path))


class StaticServer(BaseServer):
    def __init__(
        self,
        address,
        port,
        retries,
        timeout,
        root,
        handler_stats_callback,
        server_stats_callback=None,
    ):
        self._root = root
        self._handler_stats_callback = handler_stats_callback
        super().__init__(address, port, retries, timeout, server_stats_callback)

    def get_handler(self, server_addr, peer, path, options):
        return StaticHandler(
            server_addr, peer, path, options, self._root, self._handler_stats_callback
        )


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default="::", help="IP address to bind to")
    parser.add_argument("--port", type=int, default=1969, help="port to bind to")
    parser.add_argument(
        "--retries", type=int, default=5, help="number of per-packet retries"
    )
    parser.add_argument(
        "--timeout_s", type=int, default=2, help="timeout for packet retransmission"
    )
    parser.add_argument(
        "--root", type=str, default="", help="root of the static filesystem"
    )
    return parser.parse_args()


def main():
    args = get_arguments()
    logging.getLogger().setLevel(logging.DEBUG)
    server = StaticServer(
        args.ip,
        args.port,
        args.retries,
        args.timeout_s,
        args.root,
        print_session_stats,
        print_server_stats,
    )
    try:
        server.run()
    except KeyboardInterrupt:
        server.close()


if __name__ == "__main__":
    main()
