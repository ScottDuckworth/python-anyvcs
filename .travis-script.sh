#!/bin/sh
set -ex

export TEST_LOG_FILE=`mktemp`
python -m unittest tests.test_git tests.test_hg tests.test_git -v || (cat $TEST_LOG_FILE; false)
