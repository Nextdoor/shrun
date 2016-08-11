""" runner

Runs commands in yaml file

"""

from __future__ import print_function

import argparse
import atexit
import io
from multiprocessing.pool import ThreadPool
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

import termcolor
import yaml

from . import version

done_event = threading.Condition()


def print_lines(lines, prefix, color):
    for line in lines:
        termcolor.cprint(prefix, color, end='')
        print(line, end='')


def extract_tags(tags):
    if isinstance(tags, list):
        return tags
    else:
        return (tags or '').split()


def run_command(name, command, features, tmpdir, args, predicates, name_done):
    stdout_path = os.path.join(tmpdir, '{}.stdout'.format(name))
    stderr_path = os.path.join(tmpdir, '{}.stderr'.format(name))

    start_time = time.time()
    set_predicates = extract_tags(features.get('set'))

    # Wait for dependencies
    depends_on = extract_tags(features.get('depends_on'))
    while any(not name_done[d] for d in depends_on):
        with done_event:
            done_event.wait()

    if_preds = extract_tags(features.get('if'))
    unless_preds = extract_tags(features.get('unless'))

    assert not (if_preds and unless_preds), \
           "phlaml doesn't support mixing 'if' and 'unless' predicates'"

    skip = (if_preds and not any(predicates[p] for p in if_preds) or
            unless_preds and any(predicates[p] for p in unless_preds))

    termcolor.cprint('{}: {}'.format('Skipping' if skip else 'Running', command),
                     'blue' if skip else 'green')

    if skip:
        return True

    with io.open(stdout_path, 'wb') as stdout_writer, \
            io.open(stdout_path, 'rb') as stdout_reader, \
            io.open(stderr_path, 'wb') as stderr_writer, \
            io.open(stderr_path, 'rb') as stderr_reader:

        # See http://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true  # noqa
        process = subprocess.Popen(command, shell=True, executable=args.shell,
                                   stdout=stdout_writer, stderr=stderr_writer,
                                   preexec_fn=os.setsid)

        def timeout():
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            termcolor.cprint('TIMEOUT ({:0.0f})'.format(time.time() - start_time), 'red')

        timeout_seconds = features.get('timeout', args.command_timeout)
        timers = [None]

        def start_timer():
            timer = timers[0]
            if timer:
                timer.cancel()
            timer = threading.Timer(int(timeout_seconds), timeout)
            timer.start()
            timers[0] = timer

        if timeout_seconds is not None:
            start_timer()

        def print_output():
            out = stdout_reader.readlines()
            err = stderr_reader.readlines()
            print_lines(out, '| ', 'green')
            print_lines(err, ': ', 'yellow')

        while process.poll() is None:
            print_output()
            time.sleep(0.1)

        print_output()

    name = features.get('name')

    passed = not bool(process.returncode)
    for pred in set_predicates:
        predicates[pred] = passed

    elapsed_time = time.time() - start_time
    termcolor.cprint("{} {}{}({:0.1f}s)".format(
        'PASSED' if passed else 'FAILED',
        '(ignored) ' if not passed and set_predicates else '',
        '[{}] '.format(name) if name else '',
        elapsed_time),
        'green' if passed else 'red' if not set_predicates else 'cyan')

    # Make name as done
    if name:
        name_done[name] = True
        with done_event:
            done_event.notify_all()

    return passed


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(description="{} script runnner".format(__name__),
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--version', action='store_true', default=False)
    parser.add_argument('--verbose', '-v', action='store_true', default=True)
    parser.add_argument('--shell', default='/bin/bash')
    parser.add_argument('--workers', default=10, type=int, help="Number of workers.")
    parser.add_argument('--timeout', default=300, type=int, help="Seconds for the entire run.")
    parser.add_argument('--command-timeout', default=300, type=int, dest='command_timeout',
                        help="Timeout for every command.")
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

    pool = ThreadPool(args.workers)

    def timeout_handler(signal, frame):
        sys.exit(termcolor.colored("FAILED: Timed out after {} seconds".format(
            args.timeout), 'red'))

    signal.signal(signal.SIGALRM, timeout_handler)

    timer = threading.Timer(args.timeout, os.kill, (os.getpid(), signal.SIGALRM))
    timer.start()

    try:
        name_count = {}
        name_done = {}
        predicates = {}
        results = []
        for index, item in enumerate(items):
            if isinstance(item, dict):
                command, features = next(iter(item.items()))
            else:
                command = item
                features = {}

            assert isinstance(command, str), "Command '{}' must be a string".format(command)
            name = features.get('name')

            if name:
                assert name not in name_done, "name '{}' is already in use".format(name)
                name_done[name] = False
                command_name = name
            else:
                command_name = re.search('\w+', command).group(0)
                if command_name in name_count:
                    name_count[command_name] += 1
                    command_name = '{}_{}'.format(command_name, name_count[command_name])
                else:
                    name_count[command_name] = 0

            result = pool.apply_async(run_command, (), (lambda **kwargs: kwargs)(
                name=command_name, command=command, features=features, tmpdir=tmpdir, args=args,
                predicates=predicates, name_done=name_done))

            # Wait if command is synchronous
            if not (features.get('background') or name):
                result.get()

            if not features.get('background'):
                results.append(result)

        # Wait for all the threads to complete
        if not all(r.wait() is None and r.successful() and r.get() for r in results):
            exit(1)
    finally:
        timer.cancel()
        pool.terminate()

if __name__ == "__main__":
    main(sys.argv)
