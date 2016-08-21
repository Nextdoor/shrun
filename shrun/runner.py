import collections
import contextlib
import functools
import itertools
import io
import os
import re
import subprocess
import sys
import threading
import tempfile
import time
import traceback

import termcolor

from . import command
from . import parser

COLORS = ['yellow', 'blue', 'red', 'green', 'magenta', 'cyan']


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


# See https://bugs.python.org/issue1167930 for why thread join ignores interrupts
class InterruptibleThread(threading.Thread):
    POLL_FREQ = 0.1

    def join(self, timeout=None):
        start_time = time.time()
        while not timeout or time.time() - start_time < timeout:
            super(InterruptibleThread, self).join(timeout or self.POLL_FREQ)
            if not self.is_alive():
                return
        return


class Runner(object):
    def __init__(self, tmpdir, environment, retry_interval=None, shell='/bin/bash',
                 output_timeout=None):
        self.tmpdir = tmpdir
        self._retry_interval = retry_interval
        self._shell = shell
        self._output_timeout = output_timeout
        self._procs_lock = threading.Lock()
        self._procs = []
        self._output_lock = threading.Lock()
        self._colors = collections.OrderedDict((c, 0) for c in COLORS)
        self._color_lock = threading.Lock()
        self._environment = environment
        self._name_counts = {}
        self._dead = False
        self.threads_lock = threading.Lock()
        self.threads = collections.defaultdict(list)
        self._results = []

    def kill_all(self):
        """ Returns true when it is done killing all, otherwise try again """
        with self.threads_lock:
            if any(t.isAlive() for t in itertools.chain(*self.threads.values())):
                self._dead = True
                with self._procs_lock:
                    for proc in self._procs:
                        proc.kill()
                return False
            else:
                return True

    @staticmethod
    def print_lines(lines, prefix, color):
        for line in lines:
            termcolor.cprint(prefix + line, color, end='')

    @property
    def env(self):
        env = os.environ.copy()
        env.update(self._environment)
        return env

    @property
    def output_timeout(self):
        return self._output_timeout

    def print_command(self, cmd, prefix='', color='white', message='Running'):
        with self._output_lock:  # Use a lock to keep output lines separate
            lines = cmd.split('\n')
            message += ': '
            if len(lines) > 1:
                lines = [message] + lines + ['---']
            else:
                lines = [message + lines[0]]
            for line in lines:
                termcolor.cprint('{}| {}'.format(prefix, line), color=color)

    @contextlib.contextmanager
    def using_color(self):
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

    def create_name(self, name, command):
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

    def _run(self, command, name, start_time, color, skip=False, timeout=None, ignore_status=False,
             background=False, retries=0, interval=None):

        if skip:
            self.print_command(command.command, message='Skipping')
            return True

        interval = interval or self._retry_interval

        for attempt in range(0, retries + 1):
            command_name = self.create_name(name, command.command)

            stdout_path = os.path.join(self.tmpdir, '{}_{}.stdout'.format(command_name, attempt))
            stderr_path = os.path.join(self.tmpdir, '{}_{}.stderr'.format(command_name, attempt))

            with io.open(stdout_path, 'wb') as stdout_writer, \
                    io.open(stdout_path, 'rb') as stdout_reader, \
                    io.open(stderr_path, 'wb') as stderr_writer, \
                    io.open(stderr_path, 'rb') as stderr_reader:

                # See http://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true  # noqa
                proc = subprocess.Popen(command.command, shell=True, executable=self._shell,
                                        stdout=stdout_writer, stderr=stderr_writer, env=self.env)

                with self._procs_lock:
                    self._procs.append(proc)

                prefix = name or str(proc.pid)
                self.print_command(
                    command.command,
                    message=('Retrying ({})'.format(attempt) if attempt > 0 else 'Running'),
                    prefix=prefix, color=color)

                last_output_time = time.time()

                def print_output():
                    with self._output_lock:
                        out = stdout_reader.readlines()
                        err = stderr_reader.readlines()
                        self.print_lines(out, '{}| '.format(prefix), color)
                        self.print_lines(err, '{}: '.format(prefix), color)
                        return bool(out or err)

                while proc.poll() is None:
                    saw_output = print_output()
                    current_time = time.time()
                    if (timeout is not None and current_time > last_output_time + timeout and
                            not background):
                        proc.kill()
                        termcolor.cprint('{}! OUTPUT TIMEOUT ({:0.1f}s)'.format(prefix, timeout),
                                         color, attrs=['bold'])
                    elif saw_output:
                        last_output_time = current_time

                    time.sleep(0.05)

                print_output()

                with self._procs_lock:
                    self._procs.remove(proc)

            passed = not bool(proc.returncode)

            if passed or self._dead:
                break
            elif attempt < retries:
                termcolor.cprint('{}| Retrying after {}s'.format(prefix, interval), color)
                time.sleep(interval)

        elapsed_time = time.time() - start_time
        if passed:
            message = 'Done'
        elif ignore_status:
            message = 'Failed'
        else:
            message = 'FAILED'

        termcolor.cprint('{}| {}'.format(prefix, message), attrs=(None if passed else ['bold']),
                         color=color, end='')
        termcolor.cprint(" {}({:0.1f}s)".format(
            '(ignored) ' if (not passed and ignore_status) else '', elapsed_time), color=color)

        return passed

    @functools.wraps(_run)
    def run(self, *args, **kwargs):
        with self.using_color() as color:
            return self._run(*args, color=color, **kwargs)

    @print_exceptions  # Ensure we see thread exceptions
    def _run_job(self, job, **kwargs):
        self._results.append(job.run(**kwargs))

    def start(self, cmd, shared_context):
        job = command.Job(command=cmd)
        job.synchronous_prepare(shared_context)

        thread = InterruptibleThread(
            target=self._run_job, args=(job,),
            kwargs={'runner': self, 'shared_context': shared_context})
        thread.daemon = True  # Ensure this thread doesn't outlive the main thread

        # Keep track of all running threads
        with self.threads_lock:
            if job.background:
                self.threads['background'].append(thread)
            else:
                self.threads['normal'].append(thread)

        thread.start()

        # Wait if command is synchronous
        if not (job.background or job.name):
            thread.join()

    def finish(self):
        """ Waits for non-background jobs and returns True if all jobs passed"""

        # Wait for all the non-background threads to complete
        for t in self.threads['normal']:
            t.join()

        return all(self._results)


def run_commands(commands, retry_interval=None, shell='/bin/bash', tmpdir=None, output_timeout=None,
                 environment={}):
    tmpdir = tmpdir or tempfile.gettempdir()

    assert type(commands) == list, \
        "Expected command list to be a list but got {}".format(type(commands))

    job_runner = Runner(tmpdir=tmpdir, retry_interval=retry_interval, shell=shell,
                        environment=environment, output_timeout=output_timeout)

    shared_context = command.SharedContext()

    try:
        for cmd in parser.generate_commands(commands):
            job_runner.start(cmd, shared_context=shared_context)

        return job_runner.finish()

    except KeyboardInterrupt:
        termcolor.cprint("KEYBOARD INTERRUPT", 'red', file=sys.stderr)
        return False

    finally:
        while not job_runner.kill_all():  # Keep killing procs until the threads terminate
            time.sleep(0.1)
