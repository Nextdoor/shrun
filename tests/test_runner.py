from __future__ import print_function

import mock
import os
import tempfile

import pytest  # flake8: noqa

import termcolor
import yaml

from shrun import runner


@pytest.yield_fixture
def tmpdir_as_cwd(tmpdir):
    with tmpdir.as_cwd():
        yield


def run_command(command):
    return runner.run_commands(yaml.load(command), tmpdir=tempfile.gettempdir(), environment={})


def test_runs_commands(capfd):
    """ Runs the command """
    run_command('- echo Hello')
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'Done' in out


def test_commands_stop_after_first_failing_command(capfd):
    """ No commands are run after the first failing command """
    run_command("""
        - echo "Hello" && false
        - echo "Goodbye"
    """)
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'Goodbye' not in out


def test_handles_keys_in_yaml_as_commands(capfd):
    """ The key is the command """
    run_command("""
        - echo Hello:
            background: false
        """)
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'Done' in out


def test_exits_with_error_on_failure(capfd):
    """ Reports errors """
    results = run_command("- echo bad && false")
    assert results.failed[0].command == 'echo bad && false'
    out, err = capfd.readouterr()
    assert 'bad' in out


def test_runs_job_in_background(capfd, tmpdir_as_cwd):
    """ Runs the command in the background """
    run_command("""
        - "while [ ! -f done ]; do true; done; echo DONE" :
            background: true
        - touch done
        """)
    out, err = capfd.readouterr()
    assert 'DONE' in out
    assert 'Done' in out


def test_terminated_background_job(capfd, tmpdir_as_cwd):
    """ Reports stopped background jobs as terminated without failing """
    assert run_command("""
        - "touch done && sleep 10":
            background: true
        - "while [ ! -f done ]; do true; done; echo DONE"
        """)
    out, err = capfd.readouterr()
    assert 'FAILED' not in err
    assert 'FAILED' not in out
    assert 'Terminated' in out
    assert 'DONE' in out
    assert 'Done' in out


def test_command_output_timeout(capfd):
    """ Fails if an individual command doesn't output in the timeout """
    results = run_command("""
        - "while true; do sleep 1; done":
            timeout: 0
        """)
    assert results.failed
    out, err = capfd.readouterr()
    assert 'TIMEOUT' in out


def test_command_in_parallel(capfd, tmpdir_as_cwd):
    """ Runs commands in parallel with dependencies """
    results = run_command("""
        - "while [ ! -f first ]; do touch first; done; echo First Done":
            name: first
        - "[ -f first ] && echo Second Done":
            depends_on: first
            background: true
        - touch first && echo Third Done
        """)
    assert not results.failed
    out, err = capfd.readouterr()
    assert out.index('Third Done') < out.index('Second Done')


def test_commands_stop_if_dependency_failed(capfd):
    """ Runs commands in parallel with dependencies """
    run_command("""
        - echo You will see me && false:
            name: see-me
        - echo You wont see me:
            depends_on: see-me
        """)
    out, err = capfd.readouterr()
    assert "You will see me" in out
    assert "You wont see me" not in out
    assert "NOT STARTED: The following dependencies failed: 'see-me'" in err


def test_multiple_commands_with_same_name_hits_assertion():
    """ Assert that names are unique """
    with pytest.raises(AssertionError):
        run_command("""
                - echo Hello:
                    name: hello
                - echo Hi:
                    name: hello
                """)


def test_predicates(capfd):
    """ Assert that names are unique """
    os.environ['WORD'] = 'word'
    assert run_command("""
        - "true":
            set: skip_it
        - echo Yes skipped $WORD:
            unless: skip_it
        - echo Not skipped $WORD:
            if: skip_it
        """) == ([], [], False)
    out, err = capfd.readouterr()
    assert "Yes skipped word" not in out
    assert "Not skipped word" in out


def test_dont_wait_for_background():
    """ Background jobs are just terminated if they are still running """
    failed, running, _ = run_command("""
        - sleep 10000:
            background: true
        """)
    assert not failed
    assert running


def test_invalid_key():
    """ Check that only valid keywords are used """
    with pytest.raises(AssertionError):
        run_command("""
            - sleep 10000:
                backgroundish: true
            """)


def test_retries(capfd, tmpdir_as_cwd):
    """ Retry an event """
    assert run_command("""
        - "[ -e file ] || { touch file; false; }":
            retries: 1
        """) == ([], [], False)
    out, err = capfd.readouterr()
    assert "Retrying" in out


def test_series_in_command(capfd):
    """ A separate command is generated for each series """
    run_command("- echo test{{A,B}}")
    out, err = capfd.readouterr()
    assert "testA" in out
    assert "testB" in out


def test_multiple_series_in_command(capfd):
    """ Multiple series generate the cross-product """
    run_command("- echo test{{A,B}}{{1,2}}")
    out, err = capfd.readouterr()
    assert "testA1" in out
    assert "testA2" in out
    assert "testB1" in out
    assert "testB2" in out


def test_multiple_series_in_command(capfd):
    """ Identical series are expanded together """
    run_command("- echo test{{A,B}}{{A,B}}")
    out, err = capfd.readouterr()
    assert "testAA" in out
    assert "testBB" in out
    assert "testAB" not in out


def test_series_with_name(capfd):
    """ Series are expanded in names as well """
    run_command("""
        - echo test{{A,B}}:
            name: test_name{{A,B}}
        - echo DONE:
            depends_on: test_nameA test_nameB
        """)
    out, err = capfd.readouterr()
    assert "testA" in out
    assert "test_nameA" in out
    assert "testB" in out
    assert "test_nameB" in out


def test_labeled_series(capfd):
    """ Series are expanded in named series """
    run_command("- echo test{{my_series:A,B}}{{my_series}}")
    out, err = capfd.readouterr()
    assert "testAA" in out
    assert "testBB" in out


def test_foreach(capfd):
    """ Foreach are indicated when the first entry of a sequence has key 'foreach' """
    run_command("""
        - - foreach: my_series:1,2
          - echo test{{my_series}}
        """)
    out, err = capfd.readouterr()
    assert "test1" in out
    assert "test2" in out


def test_error_during_print(capfd):
    """ Foreach are indicated when the first entry of a sequence has key 'foreach' """
    original_cprint = termcolor.cprint
    calls = []

    # Generate failures for the first 50 attempts
    def bad_cprint(*args, **kwargs):
        calls.append(1)
        if len(calls) < 50:
            raise IOError
        original_cprint(*args, **kwargs)

    with mock.patch.object(termcolor, 'cprint', bad_cprint):
        with mock.patch.object(runner, 'IO_ERROR_RETRY_INTERVAL', 0):  # Speed up test
            run_command("- echo hello{{1}}")

    assert len(calls) >= 50
    out, err = capfd.readouterr()
    assert "hello1" in out
