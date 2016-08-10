#!/usr/bin/env bats

RUNNER=flaml

setup() {
    _setup_test_directory TEST_DIR
}

_setup_tmp_directory() {
    export TMPDIR="$(mktemp -d)"
    _append_to_exit_trap "rm -rf $TMPDIR"
}

_setup_test_directory() {
    name=$1
    declare -g "$name"="$(mktemp -d)"
    _append_to_exit_trap "rm -rf ${!name}"
}

_append_to_exit_trap() {
    # Makes sure to run the existing exit handler
    trap "$1; $(trap -p EXIT | sed -r "s/trap.*?'(.*)' \w+$/\1/")" EXIT
}

@test "runs commands listed in a yaml file" {
    file=$TEST_DIR/my-test.yml
    cat > $file <<- EOF
        - echo Hello
EOF
    run $RUNNER $file
    [[ $status = 0 ]]
    [[ "$output" = "Hello" ]]
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
