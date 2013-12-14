# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>

"""Zerconf utilities for iPS Manager.

This package contains convenient class to manage zeroconf
for iPS.
"""

__author__    = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


from dbus import DBusException
from dbus.mainloop.glib import DBusGMainLoop
from tornado.options import define, options

import avahi
import dbus
import dbus.mainloop.glib
import gobject
import logging
import threading
import tornado.httpclient


define('domain', default='', help='Avahi domain', metavar='DOMAIN')

NAME = 'iPS Manager'
STYPE = '_http._tcp'


gobject.threads_init()


class IPSManagerService:

  TEXT = ''
  
  def __init__(self, port, domain=None, host=''):
    self.host = host
    self.port = port
    self.domain = domain or options.domain

  def Publish(self):
    logging.info('publishing zeroconf: (host=%s, port=%s, domain=%s)',
                 self.host, self.port, self.domain)
    bus = dbus.SystemBus()
    server = dbus.Interface(
        bus.get_object(
            avahi.DBUS_NAME,
            avahi.DBUS_PATH_SERVER),
        avahi.DBUS_INTERFACE_SERVER)

    g = dbus.Interface(
        bus.get_object(avahi.DBUS_NAME,
                       server.EntryGroupNew()),
                       avahi.DBUS_INTERFACE_ENTRY_GROUP)

    g.AddService(avahi.IF_UNSPEC, avahi.PROTO_UNSPEC,dbus.UInt32(0),
                 NAME, STYPE,
                 self.domain, self.host, dbus.UInt16(self.port),
                 IPSManagerService.TEXT)

    g.Commit()
    self.group = g

  def Unpublish(self):
    self.group.Reset()


class IPSManagerMonitor:

  def __init__(self, domain='', callback=None):
    self.domain = domain
    self.thread = threading.Thread(target=self._ProcessMonitor)
    self.thread.daemon = True
    self.start = False

    self.callback = callback

    self._ClearIPSManager()

  def _ClearIPSManager(self):
    self.name = None
    self.address = None
    self.port = None

  def Monitor(self):
    logging.info('starting zeroconf monitor')
    self.start = True
    self.thread.start()

  def Term(self):
    logging.info('terminating zeroconf monitor')
    self.start = False
    self.mainloop.quit()
    while self.thread.isAlive():
      self.thread.join(1)
    logging.info('zeroconf monitor terminated')

  def _OnItemNew(self, interface, protocol, name, stype, domain, flags):
    if name == NAME:
      logging.debug("Found service '%s' type '%s' domain '%s' at %s",
                    name, stype, domain, interface)
      self.server.ResolveService(interface, protocol, name, stype,
          domain, avahi.PROTO_UNSPEC, dbus.UInt32(0),
          reply_handler=self._OnResolved, error_handler=self._OnResolveError)

  def _OnItemRemove(self, interface, protocol, name, stype, domain, flags):
    if name == NAME:
      logging.info("Disapperd service '%s' type '%s' domain '%s' at %s",
                   name, stype, domain, interface)
      self._ClearIPSManager()

  def _OnResolved(self, *args):
    logging.debug("Resolved: %s", args)
    self.name = args[2]
    self.address = args[7]
    self.port = args[8]
    logging.info("Resolved name '%s' address '%s' port '%s'",
                 self.name, self.address, self.port)
    if self.callback is not None:
      self.callback(self.name, self.address, self.port)
 
  def _OnResolveError(self, *args):
    logging.error(args[0])

  def _InitMonitor(self):
    logging.debug("Initializing zeroconf monitor")
    self.loop = DBusGMainLoop()
    self.bus = dbus.SystemBus(mainloop=self.loop)
    self.server = dbus.Interface(self.bus.get_object(avahi.DBUS_NAME, '/'),
                                 'org.freedesktop.Avahi.Server')

    self.sbrowser = dbus.Interface(self.bus.get_object(avahi.DBUS_NAME,
        self.server.ServiceBrowserNew(avahi.IF_UNSPEC,
            avahi.PROTO_UNSPEC, STYPE, self.domain, dbus.UInt32(0))),
        avahi.DBUS_INTERFACE_SERVICE_BROWSER)

    self.sbrowser.connect_to_signal("ItemNew", self._OnItemNew)
    self.sbrowser.connect_to_signal("ItemRemove", self._OnItemRemove)

  def _ProcessMonitor(self):
    while self.start:
      try:
        self._InitMonitor()
        break
      except dbus.exceptions.DBusException, e:
        logging.warning('Failed to connect to avahi daemon: %s', str(e))
    self.mainloop = gobject.MainLoop()
    self.mainloop.run()


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  mon = IPSManagerMonitor()
  mon.Monitor()
  import time
  try:
    while True:
      logging.debug('waiting 1 sec')
      time.sleep(1)
  finally:
    mon.Term()
