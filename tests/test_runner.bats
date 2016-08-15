#!/usr/bin/env bats

RUNNER=shrun

setup() {
    _setup_test_directory TEST_DIR
}

_setup_tmp_directory() {
    export TMPDIR="$(mktemp -d)"
    _append_to_exit_trap "rm -rf $TMPDIR"
}

_setup_test_directory() {
    local name=$1
    local testdir="$(mktemp -d)"
    _append_to_exit_trap "rm -rf ${testdir}"
    declare -g "$name"="$testdir"
}

_append_to_exit_trap() {
    # Makes sure to run the existing exit handler
    trap -- '$1; bats_teardown_trap' EXIT
}

@test "runs commands listed in a yaml file" {
    file=$TEST_DIR/my-test.yml
    cat > $file <<- EOF
        - echo Hello
EOF
    run $RUNNER $file
    [[ $status = 0 ]]
    [[ "$output" = *"Hello"* ]]
}

@test "runs commands that are keys" {
    file=$TEST_DIR/my-test.yml
    cat > $file <<- EOF
        - echo Hello:
            background: false
EOF
    run $RUNNER $file
    [[ $status = 0 ]]
    [[ "$output" = *"Hello"* ]]
}

@test "reports errors" {
    file=$TEST_DIR/my-test.yml
    cat > $file <<- EOF
        - exit 1
EOF
    run $RUNNER $file
    [[ $status = 1 ]]
    [[ "$output" = *"FAILED"* ]]
}

@test "runs jobs in background when flagged as background" {
    file=$TEST_DIR/my-test.yml
    cat > $file <<- EOF
        - "while [ ! -f $TEST_DIR/done ]; do sleep 0.1; done; echo DONE":
            background: true
        - touch $TEST_DIR/done
EOF
    run $RUNNER $file
    [[ $status = 0 ]]
    [[ "$output" = *"DONE"* ]]
    [[ "$output" = *"PASSED"* ]]
}
