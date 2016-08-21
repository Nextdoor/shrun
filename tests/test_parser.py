import pytest  # flake8: noqa

from shrun import parser


def test_groups():
    """ A separate command is generated for each group """
    assert parser.expand_groups('test{{A,B}}', {}) == [('testA', {}), ('testB', {})]


def test_multiple_groups():
    """ Multiple groups generate the cross-product """
    assert parser.expand_groups('test{{A,B}}{{1,2}}', {}) == [
        ('testA1', {}), ('testA2', {}), ('testB1', {}), ('testB2', {})]


def test_multiple_identical_groups():
    """ Identical groups are expanded together """
    assert parser.expand_groups('test{{A,B}}{{A,B}}', {}) == [('testAA', {}), ('testBB', {})]


def test_groups_in_features():
    """ Groups are expanded in features """
    assert parser.expand_groups('test{{A,B}}', {'depends_on': 'name{{A,B}}'}) == [
        ('testA', {'depends_on': 'nameA'}), ('testB', {'depends_on': 'nameB'})]


def test_named_groups():
    """ Groups are expanded when their name matches an existing group. """
    assert parser.expand_groups('test{{my_group=A,B}}{{my_group}}', {}) == [
        ('testAA', {}), ('testBB', {})]


def test_named_groups_map_1_to_1():
    """ Groups are mapped 1-1 to new values if the group name matches. """
    assert parser.expand_groups('test{{my_group=A,B}}{{my_group=1,2}}', {}) == [
        ('testA1', {}), ('testB2', {})]


def test_named_groups_map_1_to_1():
    """ Groups are mapped 1-1 to new values if the group name matches. """
    with pytest.raises(AssertionError) as exc_info:
        parser.expand_groups('test{{my_group=A,B}}{{my_group=1,2,3}}', {})
    assert "Group mapping must be 1-1" in exc_info.value
