from builtins import str  # Force unicode strings

import pyparsing
import six

NON_COMMA_TOKENS = pyparsing.Combine(
    pyparsing.OneOrMore(pyparsing.Word(pyparsing.printables, excludeChars=',')))
GROUP_NAME = pyparsing.Word(pyparsing.alphas + '_') + pyparsing.Suppress(pyparsing.Literal('='))
GROUP_LIST_PARSER = (
    pyparsing.Optional(GROUP_NAME)('name') +
    (pyparsing.ZeroOrMore(NON_COMMA_TOKENS + pyparsing.Suppress(pyparsing.Literal(','))) +
     NON_COMMA_TOKENS)('items'))

GROUP_PARSER = pyparsing.nestedExpr('{{', '}}')


def _get_name(group):
    return group['name'][0] if 'name' in group else ','.join(group['items'])


def _expand_value(value, target_group, index):
    if isinstance(value, six.string_types):
        new_value = ''
        start = 0
        for match_string, match_start, match_end in list(GROUP_PARSER.scanString(value)):
            group = GROUP_LIST_PARSER.parseString(match_string[0][0])
            # If this is is the same group as the target group
            if _get_name(group) == _get_name(target_group):
                if 'name' in group:
                    items = group['items']
                    assert len(items) == len(target_group['items']), "Group mapping must be 1-1"
                else:
                    items = target_group['items']
                new_value += value[start:match_start] + items[index]
                start = match_end
        return new_value + value[start:]
    else:
        return {k: _expand_value(v, target_group, index) for k, v in value.items()}


def expand_groups(command, features):
    """ Expand groups in commands

    Args
        command: Command string
        features: Features for the command

    Returns:
        An iterator of (command, features) tuples
    """
    matches = GROUP_PARSER.scanString(command)

    try:
        group_string = next(matches)[0][0][0]
    except StopIteration:
        return [(command, features)]

    group = GROUP_LIST_PARSER.parseString(group_string)

    new_commands = []
    for index, item in enumerate(group['items']):
        new_command = _expand_value(command, group, index)
        new_features = _expand_value(features, group, index)
        new_commands.extend(expand_groups(new_command, new_features))

    return new_commands

