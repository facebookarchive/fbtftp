#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.

# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# TFTP opcodes
OPCODE_RRQ = 1
OPCODE_WRQ = 2
OPCODE_DATA = 3
OPCODE_ACK = 4
OPCODE_ERROR = 5
OPCODE_OACK = 6

# TFTP modes (encodings)
MODE_NETASCII = "netascii"
MODE_BINARY = "octet"

# TFTP error codes
ERR_UNDEFINED = 0  # Not defined, see error msg (if any) - RFC 1350.
ERR_FILE_NOT_FOUND = 1  # File not found - RFC 1350.
ERR_ACCESS_VIOLATION = 2  # Access violation - RFC 1350.
ERR_DISK_FULL = 3  # Disk full or allocation exceeded - RFC 1350.
ERR_ILLEGAL_OPERATION = 4  # Illegal TFTP operation - RFC 1350.
ERR_UNKNOWN_TRANSFER_ID = 5  # Unknown transfer ID - RFC 1350.
ERR_FILE_EXISTS = 6  # File already exists - RFC 1350.
ERR_NO_SUCH_USER = 7  # No such user - RFC 1350.
ERR_INVALID_OPTIONS = 8  # One or more options are invalid - RFC 2347.

# TFTP's block number is an unsigned 16 bit integer so for large files and
# small window size we need to support rollover.
MAX_BLOCK_NUMBER = 65535

# this is the default blksize as defined by RFC 1350
DEFAULT_BLKSIZE = 512

# Metric-related constants
# How many seconds to aggregate before sampling datapoints
DATAPOINTS_INTERVAL_SECONDS = 60
