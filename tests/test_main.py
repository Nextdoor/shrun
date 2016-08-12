from __future__ import print_function

import os

import pytest  # flake8: noqa

from phlaml import main
from phlaml import version


@pytest.yield_fixture(autouse=True)
def tmpdir_as_cwd(tmpdir):
    with tmpdir.as_cwd():
        yield


def test_runs_commands_in_a_file(capfd, tmpdir):
    """ Runs the command """
    with open('test.yml', 'w') as f:
        print('- echo Hello', file=f)
    main.main(('this-command', f.name))
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
    main.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'PASSED' in out


def test_version_shows_version(capfd):
    """ Runs the command """
    with pytest.raises(SystemExit) as exc_info:
        main.main(('this-command', '--version'))
    out, err = capfd.readouterr()
    assert out == version.VERSION + '\n'
    assert exc_info.value.code == 0

def test_exits_with_error_on_failure(capfd, tmpdir):
    """ Reports errors """
    with open('test.yml', 'w') as f:
        print("""
- echo bad && false
""", file=f)
    with pytest.raises(SystemExit) as exc_info:
        main.main(('this-command', f.name))
    assert 'FAILED' in exc_info.value.message
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
    main.main(('this-command', 'test.yml'))
    out, err = capfd.readouterr()
    assert 'DONE' in out
    assert 'PASSED' in out


def test_timeout(capfd):
    """ Fails if the entire sequence doesn't complete in the timeout """
    with open('test.yml', 'w') as f:
        print('- while true; do sleep 1; done', file=f)
    with pytest.raises(SystemExit) as exc_info:
        main.main(('this-command', '--timeout', '0', f.name))
    assert 'FAILED' in exc_info.value.message


def test_command_output_timeout(capfd):
    """ Fails if an individual command doesn't output in the timeout """
    with open('test.yml', 'w') as f:
        print("""
            - "while true; do sleep 1; done":
                timeout: 0
            """, file=f)
    with pytest.raises(SystemExit):
        main.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert 'TIMEOUT' in out


def test_global_command_output_timeout(capfd):
    """ Fails if an individual command doesn't output in the global command timeout """
    with open('test.yml', 'w') as f:
        print('- while true; do sleep 1; done', file=f)
    with pytest.raises(SystemExit):
        main.main(('this-command', '--output-timeout', '0', 'test.yml'))
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
    main.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert out.index('Third Done') < out.index('Second Done')


def test_multiple_commands_with_same_name_hits_assertion():
    """ Assert that names are unique """
    with open('test.yml', 'w') as f:
        print("""
            - echo Hello:
                name: hello
            - echo Hi:
                name: hello
            """, file=f)
    with pytest.raises(AssertionError):
        main.main(('this-command', f.name))


def test_predicates(capfd):
    """ Assert that names are unique """
    os.environ['WORD'] = 'word'
    with open('test.yml', 'w') as f:
        print("""
            - "true":
                set: skip_it
            - echo Yes skipped $WORD:
                unless: skip_it
            - echo Not skipped $WORD:
                if: skip_it
            """, file=f)
    main.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert "Yes skipped word" not in out
    assert "Not skipped word" in out


def test_dont_wait_for_background(capfd):
    """ Background jobs are just terminated if they are still running """
    with open('test.yml', 'w') as f:
        print("""
            - sleep 10000:
                background: true
            """, file=f)
    main.main(('this-command', f.name))


def test_invalid_key(capfd):
    """ Check that only valid keywords are used """
    with open('test.yml', 'w') as f:
        print("""
            - sleep 10000:
                backgroundish: true
            """, file=f)
    with pytest.raises(AssertionError):
        main.main(('this-command', f.name))


def test_environment(capfd):
    """ Environment can be set with environment key """
    os.environ['GOOSE'] = 'goose'
    with open('test.yml', 'w') as f:
        print("""
            environment:
                GOOSE: $GOOSE
            main:
                - echo duck $GOOSE
            """, file=f)
    main.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert "duck goose" in out


def test_main_and_post(capfd):
    """ Post is executed even if main fails  """
    with open('test.yml', 'w') as f:
        print("""
            main:
                - "false"
            post:
                - echo Ran ${no:-yes}
            """, file=f)
    with pytest.raises(SystemExit):
        main.main(('this-command', f.name))
    out, err = capfd.readouterr()
    assert "Ran yes" in out


def test_main_and_post_with_keyboard_interrupt(capfd):
    """ Post is executed even if there is a keyboard interrupt in main  """
    with open('test.yml', 'w') as f:
        print("""
            main:
                - PID=$$; kill -INT $(ps -o ppid= -p $PID)
                - sleep 10
            post:
                - echo Ran ${no:-yes}
            """, file=f)
    with pytest.raises(SystemExit) as exc_info:
        main.main(('this-command', f.name))
    assert "FAILED" in exc_info.value.message
    out, err = capfd.readouterr()
    assert "KEYBOARD INTERRUPT" in err
    assert "Ran yes" in out
