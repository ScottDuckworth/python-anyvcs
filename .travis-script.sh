#!/bin/sh
set -x

if [ "x${TEST_SCRIPTS}" = "x" ]; then
  TEST_SCRIPTS=tests/test_*.py
fi

export TEST_LOG_FILE=`mktemp`
status=0
for script in ${TEST_SCRIPTS}; do
  python "${script}"
  status=$(( ${status} + $? ))
done

if [ ${status} -ne 0 ]; then
  cat ${TEST_LOG_FILE}
fi
exit ${status}
