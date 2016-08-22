import collections

import pyparsing
import six

KEYWORDS = ['background', 'depends_on', 'if', 'name', 'set', 'timeout', 'unless', 'retries',
            'interval']

NON_COMMA_TOKENS = pyparsing.Combine(
    pyparsing.OneOrMore(pyparsing.Word(pyparsing.printables, excludeChars=',')))
GROUP_NAME = pyparsing.Word(pyparsing.alphas + '_') + pyparsing.Suppress(pyparsing.Literal(':'))
GROUP_LIST_PARSER = (
    pyparsing.Optional(GROUP_NAME)('label') +
    (pyparsing.ZeroOrMore(NON_COMMA_TOKENS + pyparsing.Suppress(pyparsing.Literal(','))) +
     NON_COMMA_TOKENS)('items'))

GROUP_PARSER = pyparsing.nestedExpr('{{', '}}')


def _expand_value(value, target_group, index):
    if isinstance(value, six.string_types):
        new_value = ''
        start = 0
        for match_string, match_start, match_end in list(GROUP_PARSER.scanString(value)):
            group = GROUP_LIST_PARSER.parseString(match_string[0][0])
            # If this is is the same group as the target group
            if _get_label(group) == _get_label(target_group):
                if 'label' in group:
                    items = group['items']
                    assert len(items) == len(
                        target_group['items']), "Group mapping must be 1-1"
                else:
                    items = target_group['items']
                new_value += value[start:match_start] + items[index]
                start = match_end
        return new_value + value[start:]
    else:
        return {k: _expand_value(v, target_group, index) for k, v in value.items()}


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

    def expand_group(self, group, index):
        return Command(command=_expand_value(self.command, group, index),
                       features=_expand_value(self.features, group, index))

    def generate_all_commands(self):
        """ Generates a command for each item-permutation of present groups

        Yields:
            Command objects
        """
        matches = GROUP_PARSER.scanString(self.command)

        try:
            group_string = next(matches)[0][0][0]
        except StopIteration:
            yield self
        else:
            group = GROUP_LIST_PARSER.parseString(group_string)

            for index, item in enumerate(group['items']):
                for command in self.expand_group(group, index).generate_all_commands():
                    yield command


def _get_label(group):
    return group['label'][0] if 'label' in group else ','.join(group['items'])


def _generate_commands_for_sequence(sequence, groups_with_index=()):
    assert sequence and isinstance(sequence[0], dict), "Group must start with an object"
    repeat = sequence[0].get('repeat')
    group = GROUP_LIST_PARSER.parseString(repeat)
    assert _get_label(group) not in [_get_label(g) for g, _ in groups_with_index], (
        "Group '{}' is already defined in a parent sequence".format(_get_label(group)))
    for index, item in enumerate(group['items']):
        new_groups_with_index = list(groups_with_index) + [(group, index)]
        for command in sequence[1:]:
            if isinstance(command, list):  # nested sequence
                for new_command in _generate_commands_for_sequence(command, new_groups_with_index):
                    yield new_command
            else:
                new_command = Command(command)
                for group, group_idx in new_groups_with_index:
                    new_command = new_command.expand_group(group, group_idx)
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
