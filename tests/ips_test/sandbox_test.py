# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>

__author__ = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


import doctest
import ips.sandbox
import unittest

  
class FakeStub:

  Cmds = {
      'lxc-info -n example': 'example',
      'lxc-shutdown -r -n example': '',
      'lxc-shutdown -n example': '',
      'lxc-stop -n example': '',
      'lxc-start -d -n example': 'started',
      'lxc-destroy -n example': '',
      'grep lxc.network.link /var/lib/lxc/example/config | cut -d"=" -f2':
          'lxcbr0',
      'grep lxc.network.hwaddr /var/lib/lxc/example/config |' + 
          ' cut -d" " -f3': '00:11:22:33:44:55',
      'grep "00:11:22:33:44:55" /var/lib/misc/dnsmasq*.leases |' +
          ' cut -d" " -f3': '192.168.1.1',
      '(ping6 -c 1 -I lxcbr0 ff02::1 && ip -6 neigh show) |' +
          ' grep 00:11:22:33:44:55 | cut -d" " -f1':
              'fe80::213:72ff:fedc:7fb4',
      '/sbin/iptables -L PREROUTING -t nat -n': '',
      '/sbin/iptables -I PREROUTING -t nat -p tcp -d 192.168.1.254' +
          ' --dport 1 -jDNAT --to-destination 192.168.1.1': '',
      '/sbin/iptables -I OUTPUT -t nat -p tcp -d 192.168.1.254' +
          ' --dport 1 -jDNAT --to-destination 192.168.1.1': '',
      '/sbin/iptables -I PREROUTING -t nat -p tcp -d 192.168.1.254' +
          ' --dport 2 -jDNAT --to-destination 192.168.1.1': '',
      '/sbin/iptables -I OUTPUT -t nat -p tcp -d 192.168.1.254' +
          ' --dport 2 -jDNAT --to-destination 192.168.1.1': '',
      '/sbin/iptables -I PREROUTING -t nat -p tcp -d 192.168.1.254' +
          ' --dport 3 -jDNAT --to-destination 192.168.1.1': '',
      '/sbin/iptables -I OUTPUT -t nat -p tcp -d 192.168.1.254' +
          ' --dport 3 -jDNAT --to-destination 192.168.1.1': '',
      'update-alternatives --remove ips-sandbox_. /var/lib/lxc/example': '',
      'lxc-info -n example | grep state:': 'state: RUNNING',
  }

  File = {
      '/var/lib/lxc/example/sandbox.proto': 'sandbox_id: "example"',
      '/var/lib/lxc/example/ports': '1\n2 statusz\n3',
      '/var/lib/lxc/example/config': '',
      '/proc/sys/net/ipv6/conf/lxcbr0/accept_ra': '2', 
  }

  URL = {
      'http://192.168.1.1:2/healthz': 'ok',
  }

  def Exists(self, path):
    return self.__class__.File.has_key(path)

  def ReadFile(self, path):
    return self.__class__.File[path]

  def UrlRead(self, url):
    return self.__class__.URL[url]

  def HostAddress(self):
    return '192.168.1.254'

  def ExecCommand(self, cmd):
    return self.__class__.Cmds[cmd]


ips.sandbox.Sandbox._stub = FakeStub()


def suite():
  suite = unittest.TestSuite()
  suite.addTests(doctest.DocTestSuite(ips.sandbox))
  return suite
