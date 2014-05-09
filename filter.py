#!/usr/bin/env python

import getopt
import itertools
import os
import pcappy
import pcappy.types
import sys

import utils


def usage():
    print r"""
filter.py [ OPTIONS ] [ pcap file... ]

Read pcap data from stdin or given files, run it through a BPF filter
and write matching packets to stdout as pcap.

Options are:
  -h, --help          print this message
  -b, --bytecode      filter with given BPF bytecode
  -e, --expr          fitler with given BPF expression
  -c, --compile FILE  compile given bpf file and use as filter

For example to select only IP packets you can use:

    filter.py -e "ip"
    filter.py -b "4,40 0 0 12,21 0 1 2048,6 0 0 65535,6 0 0 0,"

Where the bytecode might have been generated by tcpdump:

    sudo tcpdump -p -n -ddd -i eth0 "ip" |tr "\n" ","
""".lstrip()
    sys.exit(2)


def bpf_from_bytecode(bytecode):
    instructions = bytecode.strip(",").split(',')[1:]

    class X: pass
    bpf = X()
    bpf._bpf = pcappy.types.bpf_program()
    bpf._bpf.bf_len = len(instructions)
    bpf._bpf.bf_insns = (pcappy.types.bpf_insn * (len(instructions)+10))()
    for i, ins_txt in enumerate(instructions):
        r = bpf._bpf.bf_insns[i]
        r.code, r.jt, r.jf, r.k = map(int, itertools.chain(ins_txt.split(), (0,0,0)))[:4]
    return bpf


def bpf_from_expr(expr):
    return pcappy.PcapPyBpfProgram(expr, 0,  '0.0.0.0',
                                   linktype=pcappy.LINKTYPE_ETHERNET,
                                   snaplen=65536)


def main():
    bpf = None

    try:
        opts, args = getopt.getopt(sys.argv[1:], "he:b:c:",
                                   ["help", "expr=", "bytecode=", "compile="])
    except getopt.GetoptError as err:
        print str(err)
        usage()

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-e", "--expr"):
            bpf = bpf_from_expr(a)
        elif o in ("-b", "--bytecode"):
            bpf = bpf_from_bytecode(a)
        elif o in ("-c", "--compile"):
            x = open(a, 'rb') # check if can open
            bpf = bpf_from_bytecode(utils.bpf_compile(x.read()))
        else:
            assert False, "unhandled option"

    if not args:
        readfds = [sys.stdin]
    else:
        readfds = [open(fname, 'rb') for fname in args]

    dump = pcappy.PcapPyDead(snaplen=65536).dump_open(sys.stdout)

    for fd in readfds:
        p = pcappy.open_offline(fd)
        if bpf:
            p.filter = bpf

        while True:
            try:
                r = p.next_ex()
            except pcappy.PcapPyException:
                break
            if r is None:
                break

            hdr, data = r
            dump.write(hdr, data)

    sys.stdout.flush()
    dump.flush()

    # normal exit crashes due to a double free error in pcappy
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except IOError, e:
        if e.errno == 32:
            os._exit(-1)
        raise
    except KeyboardInterrupt:
        os._exit(-1)
