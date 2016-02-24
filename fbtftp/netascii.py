# Copyright (c) 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import io


class NetasciiReader(object):
    """
    NetasciiReader encodes data coming from a reader into NetASCII.

    If the size of the returned data needs to be known in advance this will
    actually have to load the whole content of its underlying reader into memory
    which is suboptimal but also the only way in which we can make NetASCII work
    with the 'tsize' TFTP extension.

    Note:
        This is an internal class and should not be modified.
    """

    def __init__(self, reader):
        self._reader = reader
        self._buffer = bytearray()
        self._slurp = None
        self._size = None

    def read(self, size):
        if self._slurp is not None:
            return self._slurp.read(size)
        data, buffer_size = bytearray(), 0
        if self._buffer:
            buffer_size = len(self._buffer)
            data.extend(self._buffer)
        for char in self._reader.read(size - buffer_size):
            if char == ord('\n'):
                data.extend([ord('\r'), ord('\n')])
            elif char == ord('\r'):
                data.extend([ord('\r'), 0])
            else:
                data.append(char)
        self._buffer = bytearray(data[size:])
        return data[:size]

    def close(self):
        self._reader.close()

    def size(self):
        if self._size is not None:
            return self._size
        slurp, size = io.BytesIO(), 0
        while True:
            data = self.read(512)
            if not data:
                break
            size += slurp.write(data)
        self._slurp, self._size = slurp, size
        self._slurp.seek(0)
        return size
