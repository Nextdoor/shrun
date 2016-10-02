""" runner

Runs commands in yaml file

"""

from __future__ import print_function

import argparse
import functools
import os
import shutil
import signal
import sys
import tempfile
import threading
import traceback

import termcolor
import yaml

from . import runner
from . import version


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(description="{} script runnner".format(__name__),
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--version', action='store_true', default=False)
    parser.add_argument('--verbose', '-v', action='store_true', default=True)
    parser.add_argument('--shell', default='/bin/bash')
    parser.add_argument('--timeout', type=int, help="Seconds for the entire run.")
    parser.add_argument('--retry_interval', default=1, type=int, help="Seconds between retries.")
    parser.add_argument('--output-timeout', default=300, type=int, dest='output_timeout',
                        help="Timeout for any background job not generating output.")
    parser.add_argument('file', nargs='?',
                        help="File to run")

    args = parser.parse_args(argv[1:])
    if args.version:
        print(version.VERSION)
        exit(0)

    with open(args.file, 'r') as f:
        data = yaml.load(f.read())

    if isinstance(data, dict):
        environment = data.get('environment', {})
        commands = data.get('main')
    else:
        environment = {}
        commands = data

    environment = {k: os.path.expandvars(v) for k, v in environment.items()}

    tmpdir = tempfile.mkdtemp()

    def timeout_handler():
        termcolor.cprint("FAILED: Timed out after {} seconds".format(args.timeout), 'red',
                         file=sys.stderr)
        os.kill(os.getpid(), signal.SIGTERM)

    def terminate(signum, frame):
        sys.exit("FAILED")

    signal.signal(signal.SIGTERM, terminate)

    if args.timeout is not None:
        timer = threading.Timer(args.timeout, timeout_handler)

    run = functools.partial(
        runner.run_commands, shell=args.shell, retry_interval=args.retry_interval, tmpdir=tmpdir,
        environment=environment, output_timeout=args.output_timeout)

    try:
        if args.timeout is not None:
            timer.start()
        results = run(commands)
        if results.interrupt:
            termcolor.cprint("KEYBOARD INTERRUPT", 'red', file=sys.stderr)

        if results.failed:
            failed_command = results.failed[0]
        elif results.interrupt and results.running:
            failed_command = results.running[-1]
        else:
            failed_command = None

        if isinstance(data, dict):
            post_commands = data.get('post', [])
        else:
            post_commands = []

        if post_commands:
            termcolor.cprint("Running 'post' commands")
            run(post_commands)

        if failed_command:
            sys.exit(termcolor.colored(
                "FAILED: Failed while running '{}'".format(failed_command.command),
                'red'))

    finally:
        if args.timeout is not None:
            timer.cancel()

        def show_error(func, path, exc_info):
            termcolor.cprint("Unable to remove '{}'. Got '{}'".format(
                path, traceback.format_exception_only(*exc_info[0:2])), file=sys.stderr)
        shutil.rmtree(tmpdir, onerror=show_error)

if __name__ == "__main__":
    main(sys.argv)
