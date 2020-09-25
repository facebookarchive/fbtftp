[![Build Status](https://travis-ci.org/facebook/fbtftp.svg?branch=master)](https://travis-ci.org/facebook/fbtftp)
[![codebeat badge](https://codebeat.co/badges/2d4c7650-4752-4adf-a570-1948ecb4d6a8)](https://codebeat.co/projects/github-com-facebook-fbtftp)

# What is fbtftp?

`fbtftp` is Facebook's implementation of a dynamic TFTP server framework. It
lets you create custom TFTP servers and wrap your own logic into it in a very
simple manner.
Facebook currently uses it in production, and it's deployed at global scale
across all of our data centers.

# Why did you do that?

We love to use existing open source software and to contribute upstream, but
sometimes it's just not enough at our scale. We ended up writing our own tftp
framework and decided to open source it.

`fbtftp` was born from the need of having an easy-to-configure and
easy-to-expand TFTP server, that would work at large scale. The standard
`in.tftpd` is a 20+ years old piece of software written in C that is very
difficult to extend.

`fbtftp` is written in `python3` and lets you plug your own logic to:

* publish per session and server wide statistics to your infrastructure
* define how response data is built:
  * can be a file from disk;
  * can be a file created dynamically;
  * you name it!

# How do you use `fbtftp` at Facebook?

We created our own Facebook-specific server based on the framework to:

* stream static files (initrd and kernels) from our http repositories (no need
  to fill your tftp root directory with files);
* generate grub2 per-machine configuration dynamically (no need to copy grub2
  configuration files on disk);
* publish per-server and per-connection statistics to our internal monitoring
  systems;
* deployment is easy and "container-ready", just copy the application somewhere,
  start it and you are done.

# Is it better than the other TFTP servers?

It depends on your needs! `fbtftp` is written in Python 3 using a
multiprocessing model; its primary focus is not speed, but flexibility and
scalability. Yet it is fast enough at our datacenter scale :)
It is well-suited for large installations where scalability and custom features
are needed.

# What does it support?

The framework implements the following RFCs:

* [RFC 1350](https://tools.ietf.org/html/rfc1350) (the main TFTP specification)
* [RFC 2347](https://tools.ietf.org/html/rfc2347) (Option Extension)
* [RFC 2348](https://tools.ietf.org/html/rfc2348) (Blocksize option)
* [RFC 2349](https://tools.ietf.org/html/rfc2349) (Timeout Interval and Transfer
  Size Options).

Note that the server framework only support RRQs (read only) operations.
(Who uses WRQ TFTP requests in 2019? :P)

# How does it work?

All you need to do is understanding three classes and two callback functions,
and you are good to go:

* `BaseServer`: This class implements the process which deals with accepting new
  requests on the UDP port provided. Default TFTP parameters like timeout, port
  number and number of retries can be passed. This class doesn't have to be used
  directly, you must inherit from it and override `get_handler()` method to
  return an instance of `BaseHandler`.
  The class accepts a `server_stats_callback`, more about it below. the callback
  is not re-entrant, if you need this you have to implement your own locking
  logic. This callback is executed periodically and you can use it to publish
  server level stats to your monitoring infrastructure. A series of predefined
  counters are provided. Refer to the class documentation to find out more.

* `BaseHandler`: This class deals with talking to a single client. This class
  lives into its separate process, process which is spawned by the `BaserServer`
  class, which will make sure to reap the child properly when the session is
  over. Do not use this class as is, instead inherit from it and override the `get_response_data()` method. Such method must return an instance of a subclass of `ResponseData`.

* `ResponseData`: it's a file-like class that implements `read(num_bytes)`,
  `size()` and `close()`. As the previous two classes you'll have to inherit
  from this and implement those methods. This class basically let you define how
  to return the actual data

* `server_stats_callback`: function that is called periodically (every 60
  seconds by default). The callback is not re-entrant, if you need this you have
  to implement your own locking logic. This callback is executed periodically
  and you can use it to publish server level stats to your monitoring
  infrastructure. A series of predefined counters are provided.
  Refer to the class documentation to find out more.

* `session_stats_callback`: function that is called when a client session is
  over.

# Requirements

* Linux (or any system that supports [`epoll`](http://linux.die.net/man/4/epoll))
* Python 3.x

# Installation

`fbtftp` is distributed with the standard `distutils` package, so you can build
it with:

```
python setup.py build
```

and install it with:

```
python setup.py install
```

Be sure to run as root if you want to install `fbtftp` system wide. You can also
use a `virtualenv`, or install it as user by running:

```
python setup.py install --user
```

# Example

Writing your own server is simple. Let's take a look at how to write a simple
server that serves files from disk:

```python
from fbtftp.base_handler import BaseHandler
from fbtftp.base_handler import ResponseData
from fbtftp.base_server import BaseServer

import os

class FileResponseData(ResponseData):
    def __init__(self, path):
        self._size = os.stat(path).st_size
        self._reader = open(path, 'rb')

    def read(self, n):
        return self._reader.read(n)

    def size(self):
        return self._size

    def close(self):
        self._reader.close()

def print_session_stats(stats):
    print(stats)

def print_server_stats(stats):
    counters = stats.get_and_reset_all_counters()
    print('Server stats - every {} seconds'.format(stats.interval))
    print(counters)

class StaticHandler(BaseHandler):
    def __init__(self, server_addr, peer, path, options, root, stats_callback):
        self._root = root
        super().__init__(server_addr, peer, path, options, stats_callback)

    def get_response_data(self):
        return FileResponseData(os.path.join(self._root, self._path))

class StaticServer(BaseServer):
    def __init__(self, address, port, retries, timeout, root,
                 handler_stats_callback, server_stats_callback=None):
        self._root = root
        self._handler_stats_callback = handler_stats_callback
        super().__init__(address, port, retries, timeout, server_stats_callback)

    def get_handler(self, server_addr, peer, path, options):
        return StaticHandler(
            server_addr, peer, path, options, self._root,
            self._handler_stats_callback)

def main():
    server = StaticServer(address='::', port=69, retries=3, timeout=5,
                          root='/var/tftproot', 
                          handler_stats_callback=print_session_stats,
                          server_stats_callback=print_server_stats)
    try:
        server.run()
    except KeyboardInterrupt:
        server.close()

if __name__ == '__main__':
    main()
```

# Who wrote it?

`fbtftp` was created by Marcin Wyszynski (@marcinwyszynski) and Angelo Failla <pallotron@fb.com> at Facebook Ireland.

Other honorable contributors:
* Andrea Barberio <barberio@fb.com>

# License

MIT License
