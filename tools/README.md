## Ad hoc to test tftp server

While it's not difficult to simulate bad network conditions, like packet loss and
delays,  some edge conditions are quite difficult to produce, especially cases
like "loss of the last ack".

This tool was written to mimic the loss of packets in to ways:

- Skip sending selected packets, thus pretending the packets were lost in transit
  to the server.
- Ignore receiving selected packets, as if they were lost in transit to the client.

Besides that, it works as a simple tftp client, with very basic intelligence
when dealing with actual packet losses (we are testing the server, not the network).

The command line option are pretty intuitive:

-h, --help            show this help message and exit
--server SERVER       server IP address (default: ::1)
--port PORT           server tftp port (default: udp/69)
--timeout TIMEOUT     timeout interval in seconds (default: 5)
--retries RETRIES     number of retries (default: 5)
--filename FILENAME   remote file name
--blksize BLKSIZE     block size in bytes (default: 1228)
--failreceive FAILRECEIVE [FAILRECEIVE ...]
                      list of packets which will be ignored
--failsend FAILSEND [FAILSEND ...]
                      list of packets which will not be sent
--verbose, -v         display a spinner


The options "failreceive" and "failsend" are the ones responsible for making the
tool pretend we are having network issues. Each option accepts a list os packet
indexes which will be ignored/skipped. Some examples:

--failsend 50 100 100 100

The packet exchange should look like this:

-> send ACK #49
<- receive DATA #50
|skip sending ACK #50
|timeout
-> send ACK #50
<- receive DATA #51
...
-> send ACK #99
<- receive DATA #100
|skip sending ACK #100
|timeout
|skip sending ACK #100
|timeout
|skip sending ACK #100
|timeout
-> send ACK #100
<- receive DATA #101

The equivalent logic is applied to "failreceive", where received DATA packets are
ignored (--failreceive 50):

-> send ACK #49
<- receive DATA #50 (ignored)
|timeout
-> send ACK #49 (retransmit)
<- receive DATA #50
-> send ACK #50
<- receive DATA #51

The special packet number -1 can be used to represent loosing the last ack
(as in --failsend -1) or the last DATA (--failreceive -1).

Last, the tool will not write any files. To make sure the transmission was
successful, compare the file's MD5 sum with the one calculated by the tool.
