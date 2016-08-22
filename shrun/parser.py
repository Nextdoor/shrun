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
        self._parse_results = SERIES_LIST_PARSER.parseString(value)

    @property
    def labeled(self):
        return 'label' in self._parse_results

    @property
    def label(self):
        return (self._parse_results['label'][0] if self.labeled 
                else ','.join(self._parse_results['items']))

    def __eq__(self, other):
        return self.label == other.label

    @property
    def items(self):
        return self._parse_results['items']

    def __iter__(self):
        return iter(self.items)


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
    else:
        return {k: _expand_value(v, target_series, index) for k, v in value.items()}


class Command(collections.namedtuple('Command', ['command', 'features'])):
    def __new__(cls, command, features=None):
        if isinstance(command, dict):
            value, features = next(iter(command.items()))
        else:
            value = command

        assert isinstance(value, six.string_types), "Command '{}' must be a string".format(value)

        features = features or {}

        for key in features.keys():
            assert key in KEYWORDS, "Unknown keyword '{}'".format(key)

        return super(Command, cls).__new__(cls, value, features)

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


def _generate_commands_for_sequence(sequence, series_index_pairs=()):
    assert sequence and isinstance(sequence[0], dict), "series must start with an object"
    series = _Series(sequence[0].get('foreach'))
    assert series not in [s for s, _ in series_index_pairs], (
        "series '{}' is already defined in a parent sequence".format(series.label))
    for index, item in enumerate(series):
        new_series_index_pairs = list(series_index_pairs) + [(series, index)]
        for command in sequence[1:]:
            if isinstance(command, list):  # nested sequence
                for new_command in _generate_commands_for_sequence(command, new_series_index_pairs):
                    yield new_command
            else:
                new_command = Command(command)
                for series, series_idx in new_series_index_pairs:
                    new_command = new_command.expand_series(series, series_idx)
                for cmd in new_command.generate_all_commands():
                    yield cmd


def generate_commands(commands):
    for index, item in enumerate(commands):
        if isinstance(item, list):
            for command in _generate_commands_for_sequence(item):
                yield command
            return

        for command in Command(item).generate_all_commands():
            yield command
