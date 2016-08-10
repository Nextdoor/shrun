from __future__ import print_function

import tempfile

import pytest  # flake8: noqa

from flaml import runner


def test_runs_commands_in_a_file(capfd):
    """ Runs the command """
    with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
        print('- echo Hello', file=f)
        f.flush()

        runner.main(['this-command', f.name])
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'PASSED' in out


def test_handles_keys_in_yaml_as_commands(capfd):
    """ Runs the command """
    with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
        print("""
- echo Hello:
    background: false
""", file=f)
        f.flush()

        runner.main(['this-command', f.name])
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'PASSED' in out


def test_exits_with_error_on_failure(capfd):
    """ Runs the command """
    with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
        print("""
- echo bad && false
""", file=f)
        f.flush()
        with pytest.raises(SystemExit) as exc_info:
            runner.main(['this-command', f.name])
        assert exc_info.value.code == 1
    out, err = capfd.readouterr()
    assert 'bad' in out
    assert 'FAILED' in out
