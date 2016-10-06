from __future__ import print_function
from builtins import str

import mock
import os
import shutil
import stat

import pytest  # flake8: noqa

from shrun import main
from shrun import version


@pytest.yield_fixture(autouse=True)
def tmpdir_as_cwd(tmpdir):
    with tmpdir.as_cwd():
        yield


def run_command(command, args=()):
    with open('test.yml', 'w') as f:
        f.write(command)
    main.main(('this-command',) + args + (f.name,))


def test_runs_commands_in_a_file(capfd, tmpdir):
    """ Runs the command """
    run_command('- echo Hello')
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'Done' in out


def test_handles_keys_in_yaml_as_commands(capfd, tmpdir):
    """ The key is the command """
    run_command("""
        - echo Hello:
            background: false
        """)
    out, err = capfd.readouterr()
    assert 'Hello' in out
    assert 'Done' in out


def test_version_shows_version(capfd):
    """ Runs the command """
    with pytest.raises(SystemExit) as exc_info:
        main.main(('this-command', '--version'))
    out, err = capfd.readouterr()
    assert out == version.VERSION + '\n'
    assert exc_info.value.code == 0


def test_exits_with_error_on_failure(capfd, tmpdir):
    """ Reports errors """
    with pytest.raises(SystemExit) as exc_info:
        run_command("- echo bad && false")
    assert 'FAILED' in str(exc_info.value)
    out, err = capfd.readouterr()
    assert 'bad' in out
    assert 'FAILED' in out


def test_timeout(capfd):
    """ Fails if the entire sequence doesn't complete in the timeout """
    with open('test.yml', 'w') as f:
        print('- while true; do sleep 1; done', file=f)
    with pytest.raises(SystemExit) as exc_info:
        run_command('- while true; do sleep 1; done', ('--timeout', '0'))
    assert 'FAILED' in str(exc_info.value)


def test_global_command_output_timeout(capfd):
    """ Fails if an individual command doesn't output in the global command timeout """
    with pytest.raises(SystemExit):
        run_command('- while true; do sleep 1; done', ('--output-timeout', '0'))
    out, err = capfd.readouterr()
    assert 'TIMEOUT' in out


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


def test_predicates(capfd, monkeypatch):
    """ Assert that names are unique """
    monkeypatch.setenv('WORD', 'word')
    run_command("""
        - "true":
            set: skip_it
        - echo Yes skipped $WORD:
            unless: skip_it
        - echo Not skipped $WORD:
            if: skip_it
        """)
    out, err = capfd.readouterr()
    assert "Yes skipped word" not in out
    assert "Not skipped word" in out


def test_dont_wait_for_background(capfd):
    """ Background jobs are just terminated if they are still running """
    run_command("""
        - sleep 10000:
            background: true
        """)


def test_invalid_key(capfd):
    """ Check that only valid keywords are used """
    with pytest.raises(AssertionError):
        run_command("""
            - sleep 10000:
                backgroundish: true
            """)


def test_environment(capfd, monkeypatch):
    """ Environment can be set with environment key """
    monkeypatch.setenv('GOOSE', 'goose')
    run_command("""
        environment:
            GOOSE: $GOOSE
        main:
            - echo duck $GOOSE
        """)
    out, err = capfd.readouterr()
    assert "duck goose" in out


def test_main_and_post(capfd):
    """ Post is executed even if main fails  """
    with pytest.raises(SystemExit):
        run_command("""
            main:
                - "false"
            post:
                - echo Ran ${no:-yes}
            """)
    out, err = capfd.readouterr()
    assert "Ran yes" in out


def test_main_and_post_with_keyboard_interrupt(capfd):
    """ Post is executed even if there is a keyboard interrupt in main  """
    with pytest.raises(SystemExit) as exc_info:
        run_command("""
            main:
                - PID=$$; kill -INT $(ps -o ppid= -p $PID)
                - sleep 10
            post:
                - echo Ran ${no:-yes}
            """)
    assert "FAILED" in str(exc_info.value)
    out, err = capfd.readouterr()
    assert "KEYBOARD INTERRUPT" in err
    assert "Ran yes" in out


def test_exception_during_cleanup(capfd):
    """ Report exceptions during cleanup to stderr """
    original_rmtree = shutil.rmtree
    delete_paths = []

    def make_directory_unremoveable(path, *args, **kwargs):
        os.chmod(path, stat.S_IRUSR)  # remove x permission so we can't delete directory
        delete_paths.append(path)
        return original_rmtree(path, *args, **kwargs)

    try:
        with mock.patch.object(main.shutil, 'rmtree', make_directory_unremoveable):
            run_command("- echo hello")
        out, err = capfd.readouterr()
        assert "Unable to remove" in err
    finally:
        for path in delete_paths:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IEXEC)
            shutil.rmtree(path)
