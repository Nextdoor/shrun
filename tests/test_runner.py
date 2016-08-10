from __future__ import print_function

import os

import pytest  # flake8: noqa

from phlaml import runner


@pytest.yield_fixture(autouse=True)
def tmpdir_as_cwd(tmpdir):
    with tmpdir.as_cwd():
        yield


def test_runs_commands_in_a_file(capfd, tmpdir):
    """ Runs the command """
    with open('test.yml', 'w') as f:
        print('- echo Hello', file=f)
    runner.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'PASSED' in out


def test_handles_keys_in_yaml_as_commands(capfd, tmpdir):
    """ The key is the command """
    with open('test.yml', 'w') as f:
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
    with open('test.yml', 'w') as f:
        print("""
- echo bad && false
""", file=f)
    with pytest.raises(SystemExit) as exc_info:
        runner.main(('this-command', f.name))
    assert exc_info.value.code == 1
    out, err = capfd.readouterr()
    assert 'bad' in out
    assert 'FAILED' in out


def test_runs_job_in_background(capfd):
    """ Runs the command in the background """
    with open('test.yml', 'w') as f:
        print("""
            - "while [ ! -f done ]; do true; done; echo DONE" :
                background: true
            - touch done
            """, file=f)
    runner.main(('this-command', 'test.yml'))
    out, err = capfd.readouterr()
    assert 'DONE' in out
    assert 'PASSED' in out


def test_timeout():
    """ Fails if the entire sequence doesn't complete in the timeout """
    with open('test.yml', 'w') as f:
        print('- while true; do sleep 1; done', file=f)
    with pytest.raises(SystemExit) as exc_info:
        runner.main(('this-command', '--timeout', '0', f.name))
    assert 'Timed out' in exc_info.value.message


def test_command_output_timeout(capfd):
    """ Fails if an individual command doesn't output in the timeout """
    with open('test.yml', 'w') as f:
        print("""
            - "while true; do sleep 1; done":
                timeout: 0
            """, file=f)
    with pytest.raises(SystemExit):
        runner.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'TIMEOUT' in out


def test_global_command_output_timeout(capfd):
    """ Fails if an individual command doesn't output in the global command timeout """
    with open('test.yml', 'w') as f:
        print('- while true; do sleep 1; done', file=f)
    with pytest.raises(SystemExit):
        runner.main(('this-command', '--command-timeout', '0', 'test.yml'))
    out, err = capfd.readouterr()
    assert 'TIMEOUT' in out


def test_command_in_parallel(capfd):
    """ Runs commands in parallel with dependencies """
    with open('test.yml', 'w') as f:
        print("""
            - "while [ ! -f first ]; do touch first; done; echo First Done":
                name: first
            - "[ -f first ] && echo Second Done":
                depends_on: first
                background: true
            - touch first && echo Third Done
            """, file=f)
    runner.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert out.index('Third Done') < out.index('Second Done')


def test_multiple_commands_with_same_name_hits_assertion(capfd):
    """ Assert that names are unique """
    with open('test.yml', 'w') as f:
        print("""
            - echo Hello:
                name: hello
            - echo Hi:
                name: hello
            """, file=f)
    with pytest.raises(AssertionError):
        runner.main(('this-command', f.name))
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    out, err = capfd.readouterr()
