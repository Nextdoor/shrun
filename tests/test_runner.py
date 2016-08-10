from __future__ import print_function

import tempfile

import pytest  # flake8: noqa

from phlaml import runner


def test_runs_commands_in_a_file(capfd, tmpdir):
    """ Runs the command """
    with tmpdir.join('test.yaml').open(mode='w') as f:
        print('- echo Hello', file=f)
    runner.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'PASSED' in out


def test_handles_keys_in_yaml_as_commands(capfd, tmpdir):
    """ The key is the command """
    with tmpdir.join('test.yaml').open(mode='w') as f:
        print("""
- echo Hello:
    background: false
""", file=f)
    runner.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'PASSED' in out


def test_exits_with_error_on_failure(capfd, tmpdir):
    """ Reports errors """
    with tmpdir.join('test.yaml').open(mode='w') as f:
        print("""
- echo bad && false
""", file=f)
    with pytest.raises(SystemExit) as exc_info:
        runner.main(('this-command', f.name))
    assert exc_info.value.code == 1
    out, err = capfd.readouterr()
    assert 'bad' in out
    assert 'FAILED' in out


def test_runs_job_in_background(capfd, tmpdir):
    """ Runs the command in the background """
    with tmpdir.join('test.yaml').open(mode='w') as f:
        print("""
- "while [ ! -f {done_file} ]; do true; done; echo DONE" :
    background: true
- touch {done_file}""".format(done_file=tmpdir.join('done')), file=f)
    runner.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'DONE' in out
    assert 'PASSED' in out


def test_timeout(tmpdir):
    """ Fails if the entire sequence doesn't complete in the timeout """
    with tmpdir.join('test.yaml').open(mode='w') as f:
        print('- while true; do sleep 1; done', file=f)
    with pytest.raises(SystemExit) as exc_info:
        runner.main(('this-command', '--timeout', '0', f.name))
    assert 'Timed out' in exc_info.value.message


def test_command_timeout(capfd, tmpdir):
    """ Fails if an individual command doesn't complete in the timeout """
    with tmpdir.join('test.yaml').open(mode='w') as f:
        print("""
- "while true; do sleep 1; done":
    timeout: 0
""", file=f)
    with pytest.raises(SystemExit) as exc_info:
        runner.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'TIMEOUT' in out
