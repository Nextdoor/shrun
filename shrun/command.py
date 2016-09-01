from __future__ import print_function

import sys
import threading
import time

import termcolor


class SharedContext(object):
    def __init__(self):
        self._name_result = {}
        self._predicates = {}
        self._done_event = threading.Condition()

    def register_name(self, name):
        if not name:
            return

        assert name not in self._name_result, "name '{}' is already in use".format(name)
        self._name_result[name] = None

    def wait_for_dependencies(self, depends_on):
        """ Wait for dependencies to pass

        Args:
            depends_on: A list of dependency names

        Returns:
            True when all have passed, False if any have failed
        """

        while any(self._name_result[d] is None for d in depends_on):
            with self._done_event:
                self._done_event.wait()
        return [d for d in depends_on if not self._name_result[d]]

    def mark_as_done(self, name, success):
        if name:
            self._name_result[name] = success
            with self._done_event:
                self._done_event.notify_all()

    def set_predicates(self, passed, predicates):
        for pred in predicates:
            self._predicates[pred] = passed

    def should_skip(self, if_preds, unless_preds):
        assert not (if_preds
                    and unless_preds), \
            "shrun doesn't support mixing 'if' and 'unless' predicates'"

        return (if_preds and not any(self._predicates[p] for p in if_preds) or
                unless_preds and any(self._predicates[p] for p in unless_preds))


class Job(object):
    def __init__(self, command):
        self._command = command
        self._prepared = False

    @property
    def name(self):
        return self.command.features.get('name')

    @property
    def background(self):
        return self.command.features.get('background')

    @property
    def command(self):
        return self._command

    def tags(self, key):
        return self.extract_tags(self.command.features.get(key, []))

    @staticmethod
    def extract_tags(tags):
        if isinstance(tags, list):
            return tags
        else:
            return (tags or '').split()

    def synchronous_prepare(self, shared_context):
        """ Do work that should be done before this becomes a separate thread. """
        shared_context.register_name(self.name)
        self._prepared = True

    def run(self, runner, shared_context):
        assert self._prepared, 'Be sure to run prepare first'

        start_time = time.time()

        failed_dependencies = shared_context.wait_for_dependencies(self.tags('depends_on'))
        if failed_dependencies:
            termcolor.cprint("NOT STARTED: The following dependencies failed: {}".format(
                ', '.join("'{}'".format(f) for f in failed_dependencies)
            ), 'red', file=sys.stderr)
            return False

        if_preds = self.tags('if')
        unless_preds = self.tags('unless')
        skip = shared_context.should_skip(if_preds, unless_preds)

        set_predicates = self.tags('set')

        passed = runner.run(
            self.command,
            name=self.name,
            skip=skip,
            start_time=start_time,
            timeout=(self.command.features.get('timeout', runner.output_timeout)),
            background=self.command.features.get('background', False),
            ignore_status=bool(set_predicates),
            retries=self.command.features.get('retries', 0),
            interval=self.command.features.get('interval', 1))

        shared_context.mark_as_done(self.name, passed)

        shared_context.set_predicates(passed, set_predicates)

        return passed
