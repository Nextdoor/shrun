""" runner

Runs commands in yaml file

"""

from __future__ import print_function

import argparse
import atexit
import collections
import contextlib
import functools
import itertools
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
import traceback

import termcolor
import yaml

from . import version

COLORS = ['yellow', 'blue', 'red', 'green', 'magenta', 'cyan']
KEYWORDS = ['background', 'depends_on', 'if', 'name', 'set', 'timeout', 'unless']


def print_lines(lines, prefix, color):
    for line in lines:
        termcolor.cprint(prefix + line, color, end='')


def extract_tags(tags):
    if isinstance(tags, list):
        return tags
    else:
        return (tags or '').split()


class DataManager(object):
    def __init__(self):
        self._colors = collections.OrderedDict((c, 0) for c in COLORS)
        self._name_counts = {}
        self._name_done = {}
        self._predicates = {}
        self._color_counts = collections.defaultdict(lambda: 0)
        self._color_lock = threading.Lock()
        self._done_event = threading.Condition()

    def create_command_name(self, name, command):
        if name:
            command_name = name
        else:
            command_name = re.search('\w+', command).group(0)
            if command_name in self._name_counts:
                self._name_counts[command_name] += 1
                command_name = '{}_{}'.format(command_name, self._name_counts[command_name])
            else:
                self._name_counts[command_name] = 0
        return command_name

    def wait_for_dependencies(self, depends_on):
        while any(not self._name_done[d] for d in depends_on):
            with self._done_event:
                self._done_event.wait()

    def mark_as_done(self, name):
        if name:
            self._name_done[name] = True
            with self._done_event:
                self._done_event.notify_all()

    @contextlib.contextmanager
    def checkout_color(self):
        with self._color_lock:
            # Pick the oldest color, favoring colors not in use
            color = next(
                itertools.chain((c for c, count in self._colors.items() if count == 0),
                                self._colors.items()))
            self._colors[color] = self._colors.pop(color) + 1  # Re-add at the end

        try:
            yield color
        finally:
            with self._color_lock:
                self._colors[color] -= 1
                
    def set_predicates(self, passed, predicates):
        for pred in predicates:
            self._predicates[pred] = passed

    def should_skip(self, if_preds, unless_preds):
        assert not (if_preds and unless_preds), \
            "phlaml doesn't support mixing 'if' and 'unless' predicates'"

        return (if_preds and not any(self._predicates[p] for p in if_preds) or
                unless_preds and any(self._predicates[p] for p in unless_preds))


def print_exceptions(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            traceback.print_exc()
            raise
    return wrapper


@print_exceptions
def run_command(command, features, tmpdir, args, data_manager):
    start_time = time.time()

    name = features.get('name')
    command_name = data_manager.create_command_name(name, command)

    # Wait for dependencies
    data_manager.wait_for_dependencies(extract_tags(features.get('depends_on')))

    if_preds = extract_tags(features.get('if'))
    unless_preds = extract_tags(features.get('unless'))

    skip = data_manager.should_skip(if_preds, unless_preds)

    def print_command(command, prefix='', color='white', skipped=False):
        lines = command.split('\n')
        if skipped:
            message = 'Skipping: '
        else:
            message = 'Started: '
        if len(lines) > 1:
            lines = [message] + lines + ['---']
        else:
            lines = [message + lines[0]]
        for line in lines:
            termcolor.cprint('{}| {}'.format(prefix, line), color=color)

    if skip:
        print_command(command, skipped=True)
        return True

    with data_manager.checkout_color() as color:
        stdout_path = os.path.join(tmpdir, '{}.stdout'.format(command_name))
        stderr_path = os.path.join(tmpdir, '{}.stderr'.format(command_name))

        with io.open(stdout_path, 'wb') as stdout_writer, \
                io.open(stdout_path, 'rb') as stdout_reader, \
                io.open(stderr_path, 'wb') as stderr_writer, \
                io.open(stderr_path, 'rb') as stderr_reader:

            # See http://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true  # noqa
            process = subprocess.Popen(command, shell=True, executable=args.shell,
                                       stdout=stdout_writer, stderr=stderr_writer,
                                       preexec_fn=os.setsid)

            prefix = name or str(process.pid)
            print_command(command, prefix=prefix, color=color)

            timeout_seconds = features.get('timeout', args.command_timeout)
            last_output_time = time.time()

            def print_output():
                out = stdout_reader.readlines()
                err = stderr_reader.readlines()
                print_lines(out, '{}| '.format(prefix), color)
                print_lines(err, '{}: '.format(prefix), color)
                return bool(out or err)

            while process.poll() is None:
                saw_output = print_output()
                current_time = time.time()
                if (timeout_seconds is not None and
                            current_time > last_output_time + timeout_seconds):
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    termcolor.cprint('TIMEOUT', color=color, attrs=['bold'])
                elif saw_output:
                    last_output_time = current_time

                time.sleep(0.1)

            print_output()

        set_predicates = extract_tags(features.get('set'))
        passed = not bool(process.returncode)
        data_manager.set_predicates(passed, set_predicates)

        elapsed_time = time.time() - start_time
        termcolor.cprint('{}| {}'.format(prefix, 'PASSED' if passed else 'FAILED'),
                         attrs=(None if passed else ['bold']), color=color, end='')

        termcolor.cprint(" {}({:0.1f}s)".format(
            '(ignored) ' if not passed and set_predicates else '', elapsed_time), color=color)

        data_manager.mark_as_done(features.get('name'))

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

    results = []
    data_manager = DataManager()
    timer = threading.Timer(args.timeout, os.kill, (os.getpid(), signal.SIGALRM))
    timer.start()

    try:
        for index, item in enumerate(items):
            if isinstance(item, dict):
                command, features = next(iter(item.items()))
            else:
                command = item
                features = {}

            name = features.get('name')
            if name:
                assert name not in data_manager._name_done, "name '{}' is already in use".format(name)
                data_manager._name_done[name] = False

            assert isinstance(command, str), "Command '{}' must be a string".format(command)

            for key in features.keys():
                assert key in KEYWORDS, "Unknown keyword '{}'".format(key)

            result = pool.apply_async(run_command, (), (lambda **kwargs: kwargs)(
                command=command, features=features, tmpdir=tmpdir, args=args,
                data_manager=data_manager))

            # Wait if command is synchronous
            if not (features.get('background') or features.get('name')):
                result.get()

            # Don't wait for processes explicitly marked as background
            if not features.get('background'):
                results.append(result)

        # Wait for all the threads to complete
        if not all(r.wait() is None and r.successful() and r.get() for r in results):
            exit(1)
    finally:
        timer.cancel()
        pool.terminate()
        pool.join()

if __name__ == "__main__":
    main(sys.argv)
