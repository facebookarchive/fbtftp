#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import sys
import socket
import time
import hashlib
import struct
import argparse
import traceback
from enum import Enum


class Spinner:

    positions = ["-", "\\", "|", "/"]

    def __init__(self):
        self.cur = 0

    def spin(self):
        self.cur = (self.cur + 1) % 4
        return self.positions[self.cur]

    def show(self):
        print("\r{0}".format(self.spin()), end="")
        sys.stdout.flush()


"""
Helper classes, functions and data structures
"""


class TftpException(Exception):
    pass


class TFTP(Enum):
    RRQ = 1
    DATA = 3
    ACK = 4
    ERROR = 5
    OACK = 6


def str0(v):
    """Returns a null terminated byte array"""
    if type(v) is not str:
        raise Exception("Only strings")
    b = bytearray(v, encoding="ascii")
    b.append(0)
    return b


def as2bytes(i):
    if isinstance(i, TFTP):
        i = i.value
    return struct.pack(">H", i)


def get_packet_type(pkt):
    return TFTP(int.from_bytes(pkt[0:2], byteorder="big"))


def get_packet_num(pkt):
    return int.from_bytes(pkt[2:4], byteorder="big")


def get_packet_data(pkt):
    return pkt[4:]


class TftpTester(object):
    def __init__(
        self,
        server,
        port,
        timeout,
        retries,
        filename,
        blksize,
        failsend,
        failreceive,
        verbose,
    ):
        self.server = server
        self.port = int(port)
        self.filename = filename
        self.blksize = int(blksize)
        self.output = bytearray()
        self.hash = hashlib.md5()
        self.timeout = int(timeout)
        self.retries = int(retries)
        self.failsend = [int(i) for i in failsend]
        self.failreceive = [int(i) for i in failreceive]
        self.verbose = verbose
        self.spinner = Spinner()
        self.is_closed = True

    def gen_RRQ(self):
        """Initial RRQ packet and the expected response type OACK"""
        b = bytearray(as2bytes(TFTP.RRQ))
        b.extend(str0(self.filename))
        b.extend(str0("octet"))
        b.extend(str0("tsize"))
        b.extend(str0("0"))
        b.extend(str0("blksize"))
        b.extend(str0(str(self.blksize)))
        return b

    def gen_ACK(self, num):
        """ACK packet {num} and the expected response of type DATA"""
        b = bytearray(as2bytes(TFTP.ACK))
        b.extend(as2bytes(num))
        return b

    def gen_ERROR(self, message):
        """generate ERROR packet"""
        b = bytearray(as2bytes(TFTP.ERROR))
        b.extend(as2bytes(0))
        b.extend(str0(message))
        return b

    def set_socket(self):
        self.sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        self.is_closed = False

    def send(self, packet):
        self.sock.sendto(packet, (self.server, self.port))

    def send_and_expect(self, packet, expect, cur):
        retries = 0
        while retries < self.retries:
            begin = time.time()

            if cur in self.failsend:  # pretend we sent a packet which was lost
                self.failsend.remove(cur)
            else:
                self.send(packet)

            try:
                answer, sender_addr = self.sock.recvfrom(self.blksize + 4)
                self.port = sender_addr[1]
                if self.verbose:
                    self.spinner.show()

                num = get_packet_num(answer)

                # is this the last packet?
                is_last = (
                    get_packet_type(answer) == TFTP.DATA
                    and len(get_packet_data(answer)) < self.actual_blksize
                )

                # replace -1 with the actual packet number in failreceive
                # this allows us to use the same construction for all packets
                if is_last and (-1 in self.failreceive):
                    self.failreceive[self.failreceive.index(-1)] = num

                # pretend we didn't receive any message
                if num in self.failreceive:
                    self.failreceive.remove(num)
                    delta = time.time() - begin
                    time.sleep(self.timeout - delta)
                    raise socket.timeout()

                # if it's the next DATA or an OACK, we're good
                if get_packet_type(answer) == expect:
                    if (expect == TFTP.DATA and num == cur + 1) or (
                        expect == TFTP.OACK
                    ):
                        break
                elif get_packet_type(answer) == TFTP.ERROR:
                    raise TftpException(answer[4:-1].decode("ascii"))
                else:
                    print("\nUnexpected packet received. Ignoring")
            except socket.timeout:
                retries += 1
        return answer

    def loop(self):
        finished = False
        current = 0
        data = self.send_and_expect(self.gen_RRQ(), TFTP.OACK, current)
        oack = data.decode("ascii").split("\x00")
        self.actual_blksize = int(oack[4])

        while not finished:
            resp = self.send_and_expect(self.gen_ACK(current), TFTP.DATA, current)
            num = get_packet_num(resp)
            data = get_packet_data(resp)
            if num > current:
                current = num
                self.hash.update(data)

            if len(data) < self.actual_blksize:
                finished = True
                # pretend the last ack was lost in transit
                while -1 in self.failsend:
                    self.failsend.remove(-1)
                    time.sleep(self.timeout)
                self.sock.sendto(self.gen_ACK(current), (self.server, self.port))
                print("\rFinished")

    def close(self):
        if not self.is_closed:
            self.sock.close()
            self.is_closed = True
            print(f"md5: {self.hash.hexdigest()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple utility to test fbtftp server")
    parser.add_argument(
        "--server", default="::1", help="server IP address " "(default: ::1)"
    )
    parser.add_argument(
        "--port", default=69, help="server tftp port " "(default: udp/69)"
    )
    parser.add_argument(
        "--timeout", default=5, help="timeout interval in seconds " "(default: 5)"
    )
    parser.add_argument(
        "--retries", default=5, help="number of retries " "(default: 5)"
    )
    parser.add_argument("--filename", required=True, help="remote file name")
    parser.add_argument(
        "--blksize", default=1228, help="block size in bytes " "(default: 1228)"
    )
    parser.add_argument(
        "--failreceive",
        default=[],
        help="list of packets which " "will be ignored",
        nargs="+",
    )
    parser.add_argument(
        "--failsend",
        default=[],
        help="list of packets which " "will not be sent",
        nargs="+",
    )
    parser.add_argument("--verbose", "-v", action="count", help="display a spinner")

    args = parser.parse_args(sys.argv[1:])

    verbose = bool(args.verbose)
    t = TftpTester(
        server=args.server,
        port=args.port,
        filename=args.filename,
        blksize=args.blksize,
        timeout=args.timeout,
        retries=args.retries,
        failsend=args.failsend,
        failreceive=args.failreceive,
        verbose=verbose,
    )
    try:
        t.set_socket()
        t.loop()
    except Exception as ex:
        t.send(t.gen_ERROR("system error"))
        if t.verbose:
            traceback.print_tb(ex)
        else:
            print(f"Error: {ex}")
    except KeyboardInterrupt:
        t.send(t.gen_ERROR("aborted by user request"))
        print("Aborted")
    finally:
        t.close()
