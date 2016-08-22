from __future__ import print_function

import os
import tempfile

import pytest  # flake8: noqa

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
    assert run_command("- echo bad && false") is False
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


def test_command_output_timeout(capfd):
    """ Fails if an individual command doesn't output in the timeout """
    assert run_command("""
            - "while true; do sleep 1; done":
                timeout: 0
            """) is False
    out, err = capfd.readouterr()
    assert 'TIMEOUT' in out


def test_command_in_parallel(capfd, tmpdir_as_cwd):
    """ Runs commands in parallel with dependencies """
    assert run_command("""
        - "while [ ! -f first ]; do touch first; done; echo First Done":
            name: first
        - "[ -f first ] && echo Second Done":
            depends_on: first
            background: true
        - touch first && echo Third Done
        """) is True
    out, err = capfd.readouterr()
    assert out.index('Third Done') < out.index('Second Done')


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
        """) is True
    out, err = capfd.readouterr()
    assert "Yes skipped word" not in out
    assert "Not skipped word" in out


def test_dont_wait_for_background():
    """ Background jobs are just terminated if they are still running """
    assert run_command("""
        - sleep 10000:
            background: true
        """) is True


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
        """) is True
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
