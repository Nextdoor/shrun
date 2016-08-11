""" runner

Runs commands in yaml file

"""

from __future__ import print_function

import argparse
import atexit
import collections
import functools
import itertools
import os
import shutil
import signal
import sys
import tempfile
import time
import threading
import traceback

import termcolor
import yaml

from . import command
from . import runner
from . import version


def print_exceptions(f):
    """ Exceptions in threads don't show a traceback so this decorator will dump them to stdout """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            termcolor.cprint(traceback.format_exc(), 'red')
            print('-' * 20)
            raise

    return wrapper


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(description="{} script runnner".format(__name__),
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--version', action='store_true', default=False)
    parser.add_argument('--verbose', '-v', action='store_true', default=True)
    parser.add_argument('--shell', default='/bin/bash')
    parser.add_argument('--timeout', default=300, type=int, help="Seconds for the entire run.")
    parser.add_argument('--output-timeout', default=300, type=int, dest='output_timeout',
                        help="Timeout for any background job not generating output.")
    parser.add_argument('file')
    args = parser.parse_args(argv[1:])
    if args.version:
        print(version.VERSION)
        exit(0)

    with open(args.file, 'r') as f:
        items = yaml.load(f.read())

    assert type(items) == list, \
        "Expected top-level object to be a list but got {}".format(type(items))

    tmpdir = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, tmpdir)

    threads_lock = threading.Lock()
    shared_context = command.SharedContext()
    job_runner = runner.Runner(tmpdir=tmpdir, args=args)

    threads = collections.defaultdict(list)

    results = []

    @print_exceptions  # Ensure we see thread exceptions
    def run_job(job, **kwargs):
        results.append(job.run(**kwargs))

    def timeout_handler():
        termcolor.cprint("FAILED: Timed out after {} seconds".format(args.timeout), 'red',
                         file=sys.stderr)
        os.kill(os.getpid(), signal.SIGTERM)

    timer = threading.Timer(args.timeout, timeout_handler)

    def cleanup():
        timer.cancel()
        while True:  # Keep killing procs until the threads terminate
            with threads_lock:
                if any(t.isAlive() for t in itertools.chain(*threads.values())):
                    job_runner.kill_all()
                    time.sleep(0.1)
                else:
                    return

    def terminate(proc, frame):
        cleanup()
        sys.exit("FAILED")

    signal.signal(signal.SIGTERM, terminate)

    timer.start()

    try:
        for index, item in enumerate(items):
            if isinstance(item, dict):
                value, features = next(iter(item.items()))
            else:
                value = item
                features = {}

            assert isinstance(value, str), "Command '{}' must be a string".format(value)

            job = command.Job(command=value, features=features, args=args)

            job.prepare(shared_context)

            thread = threading.Thread(
                target=run_job, args=(job,),
                kwargs={'runner': job_runner, 'shared_context': shared_context})
            thread.daemon = True  # Ensure this thread doesn't outlive the main thread

            # Don't wait for processes explicitly marked as background
            with threads_lock:
                if features.get('background'):
                    threads['background'].append(thread)
                else:
                    threads['normal'].append(thread)

            # Keep track of all running threads
            thread.start()

            # Wait if command is synchronous
            if not (features.get('background') or features.get('name')):
                thread.join()

        # Wait for all the non-background threads to complete
        for t in threads['normal']:
            t.join()

        if not all(results):
            sys.exit(termcolor.colored("FAILED", 'red'))

    except KeyboardInterrupt:
        sys.exit(termcolor.colored("KEYBOARD INTERRUPT", 'red'))
    finally:
        cleanup()

if __name__ == "__main__":
    main(sys.argv)
