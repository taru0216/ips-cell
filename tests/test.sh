#!/bin/sh
export PYTHONPATH=$(dirname $(find ${abs_builddir}/build -name ips))
python ${srcdir}/setup.py test
