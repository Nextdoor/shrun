import collections

import pyparsing
import six

KEYWORDS = ['background', 'depends_on', 'if', 'name', 'set', 'timeout', 'unless', 'retries',
            'interval']

NON_COMMA_TOKENS = pyparsing.Combine(
    pyparsing.OneOrMore(pyparsing.Word(pyparsing.printables, excludeChars=',')))
SERIES_NAME = pyparsing.Word(pyparsing.alphas + '_') + pyparsing.Suppress(pyparsing.Literal(':'))
SERIES_LIST_PARSER = (
    pyparsing.Optional(SERIES_NAME)('label') +
    (pyparsing.ZeroOrMore(NON_COMMA_TOKENS + pyparsing.Suppress(pyparsing.Literal(','))) +
     NON_COMMA_TOKENS)('items'))

SERIES_PARSER = pyparsing.nestedExpr('{{', '}}')


class _Series(object):
    def __init__(self, value):
        if isinstance(value, six.string_types):
            parse_results = SERIES_LIST_PARSER.parseString(value)
            self._items = parse_results['items']
            if 'label' in parse_results:
                self._label = parse_results['label'][0]
            else:
                self._label = None
        elif isinstance(value, dict):
            self._label, self._items = next(iter(value.items()))
        else:
            self._label = None
            self._items = value

    @property
    def labeled(self):
        return bool(self._label)

    @property
    def label(self):
        return self._label or ','.join(self.items)

    def __eq__(self, other):
        return self.label == other.label

    @property
    def items(self):
        return self._items

    def __iter__(self):
        return iter(self.items)

    def __repr__(self):
        repr_str = ','.join(self.items)
        if self.labeled:
            return '{}:{}'.format(self.label, repr_str)
        else:
            return repr_str


def _expand_value(value, target_series, index):
    if isinstance(value, six.string_types):
        new_value = ''
        start = 0
        for match_string, match_start, match_end in list(SERIES_PARSER.scanString(value)):
            series = _Series(match_string[0][0])
            if series == target_series:
                if series.labeled:
                    items = series.items
                    assert len(items) == len(target_series.items), (
                        "Mapping for series '{}' must be 1-1".format(target_series.label))
                else:
                    items = target_series.items
                new_value += value[start:match_start] + items[index]
                start = match_end
        return new_value + value[start:]
    elif isinstance(value, dict):
        return {k: _expand_value(v, target_series, index) for k, v in value.items()}
    else:
        return value


class Command(collections.namedtuple('Command', ['command', 'features'])):
    def __new__(cls, command, features=None):
        if isinstance(command, dict):
            assert len(list(command.items())) == 1, (
                "Command has multiple top-level keys: %s" % sorted(command.keys()))
            value, features = next(iter(command.items()))
            assert value != 'foreach', (
                "'foreach' may only be specified at the beginning of a sequence")

        else:
            value = command

        assert isinstance(value, six.string_types), "Command '{}' must be a string".format(value)

        features = features or {}

        for key in features.keys():
            assert key in KEYWORDS, "Unknown keyword '{}'".format(key)

        return super(Command, cls).__new__(cls, value.rstrip('\n'), features)

    def expand_series(self, series, index):
        return Command(command=_expand_value(self.command, series, index),
                       features=_expand_value(self.features, series, index))

    def generate_all_commands(self):
        """ Yields a command for each item-permutation of all present series """
        matches = SERIES_PARSER.scanString(self.command)

        try:
            series_string = next(matches)[0][0][0]
        except StopIteration:
            yield self
        else:
            series = _Series(series_string)

            for index, item in enumerate(series):
                for command in self.expand_series(series, index).generate_all_commands():
                    yield command


def _generate_commands_for_sequence(sequence, foreach_index_pairs=()):
    assert sequence, 'Sequence cannot be empty'

    if isinstance(sequence[0], dict):
        foreach = sequence[0].get('foreach')
        if foreach:
            foreach = _Series(foreach)
    else:
        foreach = None

    if foreach:
        assert foreach not in [s for s, _ in foreach_index_pairs], (
            "series '{}' is already defined in a parent sequence".format(foreach.label))

        for index, _ in enumerate(foreach):
            for generated_command in _generate_commands_for_sequence(
                    sequence[1:], list(foreach_index_pairs) + [(foreach, index)]):
                yield generated_command
    else:
        for item in sequence:
            if isinstance(item, (list, tuple)):
                for generated_command in _generate_commands_for_sequence(item,
                                                                         foreach_index_pairs):
                    yield generated_command
            else:
                command = Command(item)
                for series, series_idx in foreach_index_pairs:
                    command = command.expand_series(series, series_idx)
                for generated_command in command.generate_all_commands():
                    yield generated_command


def generate_commands(commands):
    for command in _generate_commands_for_sequence(commands):
        yield command
