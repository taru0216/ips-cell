#!/usr/bin/env python

from setuptools import setup

import os
import random
import sys

srcdir = '.'
if 'srcdir' in os.environ:
  srcdir = os.environ['srcdir']

sys.path.append('%s/tests' % srcdir)

setup(name='iPS',
      version='0',
      description='iPS',
      packages=['ips', 'ips.proto'],
      package_dir={'ips': '%s/common/lib/ips' % srcdir,
                   'ips.proto': 'gen/ips/proto'},
      data_files=[('share/ips-common', ['buildinfo'])],
      scripts=['%s/servers/cell/ips-cell-server' % srcdir,
               '%s/servers/manager/ips-manager' % srcdir,
               '%s/servers/varzd/varzd' % srcdir,
               '%s/tools/ips-rpc-client' % srcdir,
               '%s/tools/ips-update-manager' % srcdir,
              ],
      test_suite = 'ips_test.all_suite')
