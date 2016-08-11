from __future__ import print_function

import threading
import time

KEYWORDS = ['background', 'depends_on', 'if', 'name', 'set', 'timeout', 'unless']


class SharedContext(object):
    def __init__(self):
        self._name_done = {}
        self._predicates = {}
        self._done_event = threading.Condition()

    def register_name(self, name):
        if not name:
            return

        assert name not in self._name_done, "name '{}' is already in use".format(name)
        self._name_done[name] = False

    def wait_for_dependencies(self, depends_on):
        while any(not self._name_done[d] for d in depends_on):
            with self._done_event:
                self._done_event.wait()

    def mark_as_done(self, name):
        if name:
            self._name_done[name] = True
            with self._done_event:
                self._done_event.notify_all()

    def set_predicates(self, passed, predicates):
        for pred in predicates:
            self._predicates[pred] = passed

    def should_skip(self, if_preds, unless_preds):
        assert not (if_preds
                    and unless_preds), \
            "phlaml doesn't support mixing 'if' and 'unless' predicates'"

        return (if_preds and not any(self._predicates[p] for p in if_preds) or
                unless_preds and any(self._predicates[p] for p in unless_preds))


class Job(object):
    def __init__(self, command, features, args):
        self._command = command
        self._features = features
        self._args = args
        self._prepared = False
        for key in self._features.keys():
            assert key in KEYWORDS, "Unknown keyword '{}'".format(key)

    @property
    def name(self):
        return self._features.get('name')

    @property
    def timeout(self):
        return self._features.get('timeout', self._args.output_timeout)

    @property
    def command(self):
        return self._command

    def tags(self, key):
        return self.extract_tags(self._features.get(key, []))

    @staticmethod
    def extract_tags(tags):
        if isinstance(tags, list):
            return tags
        else:
            return (tags or '').split()

    def prepare(self, shared_context):
        shared_context.register_name(self.name)
        self._prepared = True

    def run(self, runner, shared_context):
        assert self._prepared, 'Be sure to run prepare first'

        start_time = time.time()

        shared_context.wait_for_dependencies(self.tags('depends_on'))

        if_preds = self.tags('if')
        unless_preds = self.tags('unless')
        skip = shared_context.should_skip(if_preds, unless_preds)

        set_predicates = self.tags('set')

        passed = runner.run(command=self.command, name=self.name, skip=skip,
                            start_time=start_time, timeout=self.timeout,
                            background=self._features.get('background', False),
                            ignore_status=bool(set_predicates))

        shared_context.mark_as_done(self.name)

        shared_context.set_predicates(passed, set_predicates)

        return passed
