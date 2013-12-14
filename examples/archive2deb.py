#!/usr/bin/env python


from tornado.options import define, options

import google.protobuf.text_format
import ips.proto.sandbox_pb2
import ips.tools
import ips.utils
import logging
import os
import os.path
import re
import shutil
import tempfile
import threading
import time


define('archive', default=None, metavar='PATH')
define('debug', default='False', metavar='True|False')
define('version', default=None, metavar='VERSION')


MAKEFILE = """
build:

install:
	install -d $(DESTDIR)/usr/share/ips-cell/sandbox/
	install -m644 *.tar.bz2 $(DESTDIR)/usr/share/ips-cell/sandbox/
"""


CONTROL = """
Source: %s
Section: unknown
Priority: extra
Maintainer: Masato Taruishi <taru0216@gmail.com>
Build-Depends: debhelper (>= 8.0.0)
Standards-Version: 3.9.3

Package: %s
Architecture: any
Depends: ${shlibs:Depends}, ${misc:Depends}
Description: iPS Sandbox for %s
 This is an archived package for iPS sandbox for role %s,
 you can create your new sandbox by using ips-archive system.
"""

class Archive2Deb(threading.Thread):

  def run(self):
    self.archive = options.archive
    try:
      sandbox = ips.proto.sandbox_pb2.Sandbox()
      with InArchive() as (archivedir, builddir):
        cmd = 'find %s/ -name sandbox.proto' % builddir
        proto = ips.utils.CallExternalCommand(cmd).strip()
        if os.path.exists(proto):
          with open(proto) as f:
            google.protobuf.text_format.Merge(f.read(), sandbox)
          version = options.version or sandbox.version
          self._DhMake(builddir,
                       sandbox.role, version)
          self._Dch(builddir, version)
          self._Debuild(builddir)
          ips.utils.CallExternalCommand(
              '/bin/cp %s/ips-sandbox-* .' % archivedir)
        else:
          logging.warning('No proto file found in the archive: %s', proto)
    finally:
      ips.tools.StopTool()

  def _GenFile(self, workdir, path, content):
    with open('%s/%s' % (workdir, path), 'w') as f:
      print >>f, content

  def _GenPackageName(self, role, version):
    if not ord(version[0]) in range(ord('0'), ord('9')):
      version = '0' + version

    m = re.match('(.*)([A-Z])(.*)', role)
    while m:
      role = '%s-%s%s' % (m.group(1), m.group(2).lower(), m.group(3))
      m = re.match('(.*)([A-Z])(.*)', role)
    return 'ips-sandbox-%s_%s' % (role, version)

  def _DhMake(self, workdir, role, version):

    self._GenFile(workdir, 'Makefile', MAKEFILE)

    os.rename(
        '%s/%s' % (workdir, os.path.basename(self.archive)),
        '%s/%s.tar.bz2' % (workdir, role))

    for line in ips.utils.ExternalCommand(
        'cd %s && yes | dh_make --createorig --single --packagename %s'
        % (workdir, self._GenPackageName(role, version))):
      logging.info(line.strip())

  def _Dch(self, workdir, version):
    for line in ips.utils.ExternalCommand(
        'cd %s && dch -b -v %s-%s "Based on %s"' % (
            workdir, version, time.strftime('0dev%Y%m%d'), options.archive)):
      logging.info(line.strip())

  def _Debuild(self, workdir):
    for line in ips.utils.ExternalCommand(
        'cd %s && debuild -b -us -uc' % workdir):
      logging.info(line.strip())


class InArchive:

  def __enter__(self):
    self.archive = options.archive
    self.tmpdir = tempfile.mkdtemp()
    self.builddir = '%s/build' % self.tmpdir
    os.mkdir(self.builddir)
    self._UnpackArchive()
    self._CopyArchive()
    return self.tmpdir, self.builddir

  def _UnpackArchive(self):
    cmd = 'tar --exclude rootfs -jxf %s -C %s' % (self.archive,
                                                  self.builddir)
    logging.info('extracting configurations from %s', self.archive)
    ips.utils.CallExternalCommand(cmd)

  def _CopyArchive(self):
    src = self.archive
    dest = '%s/%s' % (self.builddir, os.path.basename(src))
    logging.info('copying file from %s to %s', src, dest)
    shutil.copyfile(src, dest)

  def __exit__(self, exc_type, exc_value, traceback):
    if options.debug.lower() != 'true':
      ips.utils.CallExternalCommand('/bin/rm -rf %s' % self.tmpdir)
    return False


if __name__ == '__main__':
  ips.tools.StartTool(Archive2Deb())
