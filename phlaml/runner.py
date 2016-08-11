import collections
import contextlib
import functools
import itertools
import io
import os
import re
import subprocess
import threading
import time

import termcolor

COLORS = ['yellow', 'blue', 'red', 'green', 'magenta', 'cyan']


class Runner(object):
    def __init__(self, tmpdir, args):
        self.tmpdir = tmpdir
        self.args = args
        self._procs_lock = threading.Lock()
        self._procs = []
        self._output_lock = threading.Lock()
        self._colors = collections.OrderedDict((c, 0) for c in COLORS)
        self._color_lock = threading.Lock()
        self._name_counts = {}

    def kill_all(self):
        with self._procs_lock:
            for proc in self._procs:
                proc.kill()

    @staticmethod
    def print_lines(lines, prefix, color):
        for line in lines:
            termcolor.cprint(prefix + line, color, end='')

    def print_command(self, command, prefix='', color='white', skipped=False):
        with self._output_lock:  # Use a lock to keep output lines separate
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
             background=False):
        if skip:
            self.print_command(command, skipped=True)
            return True

        command_name = self.create_name(name, command)

        stdout_path = os.path.join(self.tmpdir, '{}.stdout'.format(command_name))
        stderr_path = os.path.join(self.tmpdir, '{}.stderr'.format(command_name))

        with io.open(stdout_path, 'wb') as stdout_writer, \
            io.open(stdout_path, 'rb') as stdout_reader, \
            io.open(stderr_path, 'wb') as stderr_writer, \
            io.open(stderr_path, 'rb') as stderr_reader:

            # See http://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true  # noqa
            proc = subprocess.Popen(command, shell=True, executable=self.args.shell,
                                    stdout=stdout_writer, stderr=stderr_writer)

            with self._procs_lock:
                self._procs.append(proc)

            prefix = name or str(proc.pid)
            self.print_command(command, prefix=prefix, color=color)

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

                time.sleep(0.1)

            print_output()

            with self._procs_lock:
                self._procs.remove(proc)

        passed = not bool(proc.returncode)

        elapsed_time = time.time() - start_time
        termcolor.cprint('{}| {}'.format(prefix, 'PASSED' if passed else 'FAILED'),
                         attrs=(None if passed else ['bold']), color=color, end='')

        termcolor.cprint(" {}({:0.1f}s)".format(
            '(ignored) ' if (not passed and ignore_status) else '', elapsed_time), color=color)

        return passed

    @functools.wraps(_run)
    def run(self, *args, **kwargs):
        with self.using_color() as color:
            return self._run(*args, color=color, **kwargs)
