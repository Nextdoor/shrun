""" runner

Runs commands in yaml file

"""

from __future__ import print_function

import argparse
import subprocess
import sys

import termcolor
import yaml

from . import version


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(description="{} script runnner".format(__name__))
    parser.add_argument('--version', action='store_true', default=False)
    parser.add_argument('--verbose', '-v', action='store_true', default=False)
    parser.add_argument('--shell', default='/bin/bash')
    parser.add_argument('file')
    args = parser.parse_args(argv[1:])
    if args.version:
        print(version.VERSION)
        exit(0)

    with open(args.file, 'r') as f:
        top = yaml.load(f.read())

    assert type(top) in (tuple, list)

    for item in top:
        if args.verbose:
            termcolor.cprint("Running: {}".format(item), 'green')
        try:
            subprocess.check_call(item, shell=True, executable=args.shell)
        except subprocess.CalledProcessError as e:
            termcolor.cprint("FAILED({})".format(e.returncode), 'red')
            exit(1)

if __name__ == "__main__":
    main(sys.argv)
