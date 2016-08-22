import pytest  # flake8: noqa
import yaml

from shrun import parser


def parse_command(command):
    return list(parser.generate_commands([command]))


def test_groups():
    """ A separate command is generated for each group """
    assert parse_command('test{{A,B}}') == [('testA', {}), ('testB', {})]


def test_multiple_groups():
    """ Multiple groups generate the cross-product """
    assert parse_command('test{{A,B}}{{1,2}}') == [
        ('testA1', {}), ('testA2', {}), ('testB1', {}), ('testB2', {})]


def test_multiple_identical_groups():
    """ Identical groups are expanded together """
    assert parse_command('test{{A,B}}{{A,B}}') == [
        ('testAA', {}), ('testBB', {})]


def test_groups_in_features():
    """ Groups are expanded in features """
    assert parse_command({'test{{A,B}}': {'depends_on': 'name{{A,B}}'}}) == [
        ('testA', {'depends_on': 'nameA'}), ('testB', {'depends_on': 'nameB'})]


def test_labeled_groups():
    """ Groups are expanded when their name matches an existing group. """
    assert parse_command('test{{my_group:A,B}}{{my_group}}') == [('testAA', {}), ('testBB', {})]


def test_labeled_groups_map_1_to_1():
    """ Groups are mapped 1-1 to new values if the group name matches. """
    assert parse_command('test{{my_group:A,B}}{{my_group:1,2}}') == [('testA1', {}), ('testB2', {})]


def test_labeled_groups_map_1_to_1():
    """ Groups are mapped 1-1 to new values if the group name matches. """
    with pytest.raises(AssertionError) as exc_info:
        parse_command('test{{my_group:A,B}}{{my_group:1,2,3}}')
    assert "Group mapping must be 1-1" in exc_info.value


def test_sequence():
    """ Sequences are expanded based using the repeat feature. """
    assert list(parser.generate_commands(yaml.load("""
        - - repeat: my_group:A,B
          - echo test{{my_group}}_{{x,y}}
          - echo test2{{my_group}}
    """))) == [('echo testA_x', {}), ('echo testA_y', {}), ('echo test2A', {}),
               ('echo testB_x', {}), ('echo testB_y', {}), ('echo test2B', {})]


def test_nested_sequences():
    """ Sequences are expanded based using the repeat feature. """
    assert list(parser.generate_commands(yaml.load("""
        - - repeat: my_group:A,B
          - - repeat: 1,2
            - echo test{{my_group}}_{{1,2}}
    """))) == [('echo testA_1', {}), ('echo testA_2', {}),
               ('echo testB_1', {}), ('echo testB_2', {})]


def test_nested_sequences_with_same_name_error():
    """ A group name cannot be used in nested sequences. """
    with pytest.raises(AssertionError) as exc_info:
        assert list(parser.generate_commands(yaml.load("""
            - - repeat: my_group:A,B
              - - repeat: my_group:1,2
                - echo test{{my_group}}
        """)))


def test_invalid_feature_key():
    """ Check that only valid keywords are used """
    with pytest.raises(AssertionError):
        parse_command({'sleep 1000': {'backgroundish': True}})
