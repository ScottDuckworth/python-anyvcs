#!/bin/sh
set -x
case "`python --version 2>&1`" in
  "Python 2.6."*)
    pip install unittest2
    ;;
esac
