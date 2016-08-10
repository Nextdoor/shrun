""" runner

Runs commands in yaml file

"""

from __future__ import print_function
from builtins import str

import argparse
import io
import os
import re
import subprocess
import sys
import tempfile
import time

import termcolor
import yaml

from . import version


def print_lines(lines, prefix, color):
    for line in lines:
        termcolor.cprint(prefix, color, end='')
        print(line, end='')


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(description="{} script runnner".format(__name__))
    parser.add_argument('--version', action='store_true', default=False)
    parser.add_argument('--verbose', '-v', action='store_true', default=True)
    parser.add_argument('--shell', default='/bin/bash')
    parser.add_argument('file')
    args = parser.parse_args(argv[1:])
    if args.version:
        print(version.VERSION)
        exit(0)

    with open(args.file, 'r') as f:
        top = yaml.load(f.read())

    assert type(top) in (tuple, list)

    tmpdir = tempfile.mkdtemp()
    name_count = {}
    failed = False
    for index, item in enumerate(top):
        if isinstance(item, dict):
            command = next(iter(item.keys()))
        else:
            command = item

        name = re.search('\w+', command).groups(0)

        if name in name_count:
            name_count[name] += 1
            name = '{}_{}'.format(name, name_count[name])
        else:
            name_count[name] = 0

        stdout_path = os.path.join(tmpdir, '{}.stdout'.format(name))
        stderr_path = os.path.join(tmpdir, '{}.stderr'.format(name))

        if args.verbose:
            termcolor.cprint("Running: {}".format(command), 'green')

        with io.open(stdout_path, 'wb') as stdout_writer, \
            io.open(stdout_path, 'rb', 1) as stdout_reader, \
            io.open(stderr_path, 'wb') as stderr_writer, \
            io.open(stderr_path, 'rb') as stderr_reader:

            start_time = time.time()
            process = subprocess.Popen(command, shell=True, executable=args.shell,
                                       stdout=stdout_writer, stderr=stderr_writer)

            def print_output():
                print_lines(stdout_reader.readlines(), '| ', 'green')
                print_lines(stderr_reader.readlines(), ': ', 'yellow')

            while process.poll() is None:
                print_output()
                time.sleep(0.1)

            print_output()

            elapsed_time = time.time() - start_time
            termcolor.cprint("{} ({:0.1f}s)".format(
                'FAILED' if process.returncode else 'PASSED',
                elapsed_time),
                'red' if process.returncode else 'green')

            if process.returncode:
                break

    if failed:
        exit(1)

if __name__ == "__main__":
    main(sys.argv)
