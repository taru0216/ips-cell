# Copyright (c) 2013 Masato Taruishi <taru0216@gmail.com>

"""sandbox.py: manages sandbox.

This module contains necessary classes and functions to manage
iPS sandbox. Sandbox is an isolated standalone linux environment and
has well-formed life-cycle definition. Sandbox has a state and
you can control it by sending 'event' such as PROVISIONING, START,
STOP, SHUTDOWN, REBOOT, ARCHIVING.

Sandbox supports the following features:

 * Life-cycle management, from born to archived.
 * Role-based version management with rollback support.
 * Inter-sandbox shared file system.
 * IPv4 auto DNAT/SNAT management.
 * IPv6 auto NDP, or Neighor Discovery Proxy management.

Typical use case to use this module would be:

 # Gets sandbox group for role 'myRole' and 'myOwner'.
 import ips.sandbox
 alternatives = ips.sandbox.GetAlternatives('myRole', 'myOwner')

 # Gets the current state of the sandbox.
 alternatives.GetCurrentSandbox().GetState()

 # Starts the sandbox.
 req = ips.proto.sandbox_pb2.SendEventRequest()
 req.event = ips.proto.sandbox_pb2.SendEventRequest.START
 res = alternatives.GetCurrentSandbox().SendEvent(req)
"""

__authour__   = "Masato Taruishi"
__copyright__ = "Copyright (c) 2013 Masato Taruishi <taru0216@gmail.com>"


from tornado.options import options, define

import google.protobuf.text_format
import ips.proto.sandbox_pb2
import ips.utils
import logging
import os
import Queue
import re
import socket
import threading
import time
import urllib


define('sandbox_vgname',
    default='',
    help='Volume group name to use for sandbox',
    metavar='VGNAME')

define('dev',
    default='eth0',
    help='device to use to provide sandbox service',
    metavar='DEVICE')

define('shared_dir',
    default='/srv/ips/users',
    help="Directory for sandbox's shared disk.",
    metavar='DIR')


class Error(Exception):
  """General exception of this module."""
  pass


class InvalidRoleName(Error):
  """Thrown when invalid role name is specified."""
  pass


class InvalidOwnerName(Error):
  """Thrown when invalid owner name is specified."""
  pass


def GetEventName(event):
  """Gets the human readable name of the specified event.

  Event is used to send a sandbox to control it from clients,
  but the event is enum integer value of protocol buffer and then
  it's hard to recognize what the number means. This function
  translates the specified enum integer number to human readable
  protocol buffer identifier.

  >>> GetEventName(0)
  'PROVISIONING'
  """
  d = ips.proto.sandbox_pb2.SendEventRequest.DESCRIPTOR
  return d.enum_types_by_name['Event'].values_by_number[event].name


def GetSandboxProto(path):
  """Returns sandbox protocol buffer."""
  sandbox = ips.proto.sandbox_pb2.Sandbox()
  if os.path.exists(path):
    with open(path) as f:
      google.protobuf.text_format.Merge(f.read(), sandbox)
  return sandbox


def GetAlternatives(role, owner):
  """Gets Alternatives instance for the specified role and owner."""
  generic_name = ips.proto.sandbox_pb2.GenericName()
  generic_name.role = role
  generic_name.owner = owner
  return Alternatives(generic_name)


class Alternatives(object):
  """Group of sandboxes.

  Alternatives is a way to group multiple sandboxes by Generic Name.
  Each sandbox joins in a group specified by GenericName and is called
  alternative in the group. Each alternative has priority in the group
  and administrators can choose one of alternatives for the target
  sandbox for the group.

  Typically, this is used to handle sandbox version up/rollback. When you
  want to upgrade your sandbox, then you can create a new sandbox which
  has higher priority in the group and restart with the new version. If
  you encounter a problem for the new version, then you can choose the
  previous sandbox as the target sandbox for the group and restart it.

  To generate Alternatives instance, you can use the classmethod
  'GetGenericName':

  >>> res = Alternatives.GetGenericNames()
  >>> if len(res.generic_names) > 0:
  ...   a = Alternatives(res.generic_names[0])

  ...   res = a.GetAlternatives()

  ...   sandbox = a.GetCurrentSandbox()

  ...   res = a.SetAlternative()

  """

  def __init__(self, generic_name_proto):
    """Instantiates with the specified GenericName proto."""
    super(self.__class__, self).__init__()
    self.proto = generic_name_proto
    self.sandboxes = {}

  def _GetInternalGenericName(self):
    return 'ips-sandbox_%s.%s' % (self.proto.role,
                                  self.proto.owner.replace('.', '-'))

  def _GetSandbox(self, sandbox_id):
    if not sandbox_id in self.sandboxes:
      self.sandboxes[sandbox_id] = Sandbox(sandbox_id)
    return self.sandboxes[sandbox_id]

  def GetCurrentSandbox(self):
    """Gets the current sandbox for this alternatives."""
    res = self.GetAlternatives()
    if res:
      return self._GetSandbox(res.current_sandbox_id)
    return None

  def GetAlternatives(self):
    """Gets a list of alternatives."""
    response = ips.proto.sandbox_pb2.GetAlternativesResponse()
    name = self._GetInternalGenericName()
    cmd = (
        'update-alternatives --query %s 2 > /dev/null | grep Status: | '
        'cut -d" " -f2' % name)
    if 'auto' == ips.utils.CallExternalCommand(cmd).strip():
      response.mode = ips.proto.sandbox_pb2.GetAlternativesResponse.AUTO
    else:
      response.mode = ips.proto.sandbox_pb2.GetAlternativesResponse.MANUAL

    cmd = (
        'basename $(LANG=C update-alternatives --display %s | grep points | '
        "awk -F' ' '{print $5;}')" % name)
    try:
      response.current_sandbox_id = ips.utils.CallExternalCommand(cmd).strip()
    except ips.utils.CommandExitedWithError:
      # No such alnatives found.
      return response

    cmd = (
        'LANG=C update-alternatives --display %s | grep priority' % name)
    try:
      for line in ips.utils.ExternalCommand(cmd):
        if line.find('/') == 0:
          alternative = response.alternatives.add()
          alternative.sandbox.CopyFrom(
              GetSandboxProto('%s/sandbox.proto' % line.split(' ')[0]))
          alternative.priority = int(line.split(' ')[3])
    except ips.utils.CommandExitedWithError:
      pass
    return response

  def SetAlternative(self, sandbox_id=None):
    """Sets the specified sandbox_id as alternative.

    This method sets the specified sandbox_id as alternative
    for this generic name. If sandbox_id is not given, auto mode
    is selected and the sandbox which has the highest priority
    becomes the alternative for this generic name.
    """
    name = self._GetInternalGenericName()

    response = ips.proto.sandbox_pb2.SetAlternativeResponse()
    try:
      if sandbox_id:
        path = '/var/lib/lxc/%s' % sandbox_id
        cmd = 'update-alternatives --set %s %s' % (name, path)
        ips.utils.CallExternalCommand(cmd)
      else:
        ips.utils.CallExternalCommand('update-alternatives --auto %s' % name)
      response.status = ips.proto.sandbox_pb2.SetAlternativeResponse.SUCCESS
    except ips.utils.CommandExitedWithError, e:
      response.status = ips.proto.sandbox_pb2.SetAlternativeResponse.FAILED
      response.description = e.out
    return response

  @classmethod
  def GetGenericNames(cls):
    """Get a list of GenericName.

    >>> res = Alternatives.GetGenericNames()
    >>> if len(res.generic_names) > 0:
    ...   s = Alternatives(res.generic_names[0])
    """
    response = ips.proto.sandbox_pb2.GetGenericNamesResponse()
    cmd = (
        'update-alternatives --get-selections | grep ips-sandbox_ | '
        'cut -d" " -f1 | cut -d_ -f2-')
    for line in ips.utils.ExternalCommand(cmd):
      generic_name = response.generic_names.add()
      generic_name.role = line.split('.')[0].replace('-', '.')
      generic_name.owner = line.strip().split('.')[1].replace('-', '.')
    return response


class Sandbox(object):
  """Sandbox

  Sandbox is an isolated standalone linux environment and has
  well-formed life-cycle definition. Sandbox has a state and
  you can control it by sending 'event' such as PROVISIONING, START,
  STOP, SHUTDOWN, REBOOT, ARCHIVING.

  In order create a sandbox instance, just instantiate this class with
  your sandbox_id. This attaches to the existing sandbox environment,
  or template environment which has NONE state if there's no such sandbox
  which has the specified id:

  >>> s = Sandbox('example')

  So you can use GetState() method to get the current status of
  this existing sandbox.

  >>> str(s.GetState())
  'state: READY\\n'

  >>> import ips.proto.sandbox_pb2
  >>> s.GetState().state == ips.proto.sandbox_pb2.READY
  True

  To control the sandbox, call SendEvent() with SendEventRequest argument.

  >>> req = ips.proto.sandbox_pb2.SendEventRequest()
  >>> req.event = ips.proto.sandbox_pb2.SendEventRequest.STOP
  >>> res = s.SendEvent(req)
  >>> str(res)
  'status: SUCCESS\\ndescription: ""\\n'

  Full list of the sandbox states are:

   NONE         : No state
   PROVISIONING : The sandbox is being created, will be to STOP
                  state when it's finished.
   FAILED       : Failed to create the sandbox.
   STOP         : The sandbox is created but not started.
   BOOT         : The sandbox is starting but hasn't been ready
                  to serve requests, will be automatically changed to
                  READY.
   READY        : The sandbox runs successfully and is ready to
                  servce requests, will be automatically changed to BOOT
                  when the sandbox is shutting down or the server process dies.
   ARCHIVING    : The sandbox is bebing archived, will be automatically
                  changed to ARCHIVED when it's finished.
   ARCHIVED     : The sandbox is archived.

  Full list of the sandbox events are:

   PROVISIONING     : Creates a new sandbox.
   START            : Starts the sandbox.
   OPEN_NETWORK     : Opens the network ports reserved for the sandbox. See
                      the next section about network for more detail below.
   LAMEDUCK_NETWORK : Lameducks the network ports. Lameduck means no new
                      connection is established but current connections
                      are alive.
   SHUTDOWN         : Shutdowns the sandbox.
   REBOOT           : Reboots the sandbox.
   STOP             : Forcebly shutdowns the sandbox.
   DESTROY          : Removes the sandbox.
   ARCHIVE          : Archives the sandbox.

  How to connect to network.

  Sandbox has its own network address, therefore it needs to route network
  packets correctly. Sandbox has different strategies for IPv4 and IPv6.

  For IPv4, because of limited number of IP addresses, the host linux
  acts as a NAT router for sandboxes running on it. For engress packets
  from sandboxes, the host linux does SNAT, or just NAT. For ingress packets
  to sandboxes, it does DNAT, i.e. the host linux network address is
  the representative address for all the sandboxes. When a sandbox is
  ready to serve requets, the host linux forward packets to decided
  ports for the sandbox by using DNAT. This means that only one sandbox
  can receive packates for one port at the same time. The event 'OPEN_NETWORK'
  does this control, it creates DNAT rules on the host linux.

  <== SNAT 10.0.0.1 == +------+ <=======================  +-------+
                       | Host |                           |Sandbox|
  === 10.0.0.1:123 ==> +------+ = DNAT 192.168.1.1:123 => +-------+
                       10.0.0.1                          192.168.1.1

  For IPv6, all sandboxes and the host linux are located in the same IPv6
  network address and the host linux acts as IPv6 neighor proxy, similar to
  bridge in IPv4. So clients can discover sandboxes by using IPv6 neighor
  discovery protocol.

  fd00:db::/64


             fd00:db::2/64        fd00::db::123/64
              +------+            +--------+
    NDP <==   | Host |=====+====> |Sandbox1|
              +------+     |      +--------+
                           |
                           |      fd00::db::456/64
                           |      +--------+
                           +====> |Sandbox2|
                                  +--------+

  This class implements sandbox interface by using lxc framework.
  LXC uses one linux kernel running on the host linux and all sandbox
  shares the same linux kernel. It can be considered as a guest os,
  but more effective than normal machine-based virtualization
  technologies. LXC sandbox uses cgroup framework in linux and
  each sandbox runs on the same linux kernel with a different namespace.
  """

  class _Stub:
    """Stub to external environment.

    This class implmenets several methods to access to external
    environment such as executing command, reading files.

    Normally, you don't have to change this class but it's convenient
    to replace with fake stub when you want to test Sandbox class.

    >>> class FakeStubExample:
    ...   def ExecCommand(self, cmd):
    ...     return 'hogehoge'

    >>> s = Sandbox('mock', stub=FakeStubExample())
    """

    def ReadFile(self, path):
      """Reads the specified file path and returns its contents."""
      if os.path.exists(path):
        with open(path) as f:
          return f.read()
      return ''

    def ExecCommand(self, cmd):
      """Executes the specified cmd with a shell."""
      return ips.utils.CallExternalCommand(cmd)

    def Exists(self, path):
      """Returns true if the specified path exists."""
      return os.path.exists(path)

    def HostAddress(self):
      """Returns the host network address."""
      return ips.utils.GetNetworkAddresses(options.dev)[0]

    def UrlRead(self, url):
      """Returns the contents from the specified URL."""
      return urllib.urlopen(url).read()

  _stub = _Stub()

  class _Worker(threading.Thread):
    """Worker thread to take a task for this sandbox.

    This worker is used to run long-life tasks such as provisioning
    and archiving.
    """

    def __init__(self):
      super(self.__class__, self).__init__()
      self.task_queue = Queue.Queue(1)
      self.task = None
      self.daemon = True

    def run(self):
      while True:
        self.task = self.task_queue.get()
        self.task.run()

  def __init__(self, sandbox_id, stub=None):
    """LXC Sandbox.

    >>> s = Sandbox('id')
    """
    super(self.__class__, self).__init__()
    self.sandbox_id = sandbox_id
    self._worker = Sandbox._Worker()
    self._worker.start()
    self._stub = stub or Sandbox._stub

  def GetSandboxProto(self):
    """Returns sandbox protocol buffer."""
    path = '/var/lib/lxc/%s/sandbox.proto' % self.sandbox_id
    return GetSandboxProto(path)

  def _EachPortConfig(self, path):
    if self._stub.Exists(path):
      ports = []
      for line in self._stub.ReadFile(path).split('\n'):
        if line.strip() != '':
          yield line.strip()

  def GetPorts(self):
    """Gets ports used by this sandbox.

    >>> s = Sandbox('example')
    >>> s.GetPorts()
    [1, 2, 3]
    """
    ports = []
    for port_config in self._EachPortConfig(
        '/var/lib/lxc/%s/ports' % self.sandbox_id):
      ports.append(int(port_config.split(' ')[0]))
    return ports

  def GetStatuszPort(self):
    """Gets the status web server port of this sandbox.

    >>> s = Sandbox('example')
    >>> s.GetStatuszPort()
    2
    """
    for port_config in self._EachPortConfig(
        '/var/lib/lxc/%s/ports' % self.sandbox_id):
      config = port_config.split(' ')
      if 'statusz' in config:
        return int(config[0])
    return None

  def _GetConfigPath(self):
    return '/var/lib/lxc/%s/config' % self.sandbox_id

  def GetNetworkLinkInterface(self):
    """Gets the network link interface of this sandbox.
 
    >>> s = Sandbox('example')
    >>> s.GetNetworkLinkInterface()
    'lxcbr0'
    """
    config_path = self._GetConfigPath()
    if self._stub.Exists(config_path):
      return self._stub.ExecCommand(
          'grep lxc.network.link %s |'
          ' cut -d"=" -f2' % config_path).strip()
    return None

  def GetNetworkHwAddress(self):
    """Gets the network hardware address.
 
    >>> s = Sandbox('example')
    >>> s.GetNetworkHwAddress()
    '00:11:22:33:44:55'
    """
    config_path = self._GetConfigPath()
    if self._stub.Exists(config_path):
      return self._stub.ExecCommand(
          'grep lxc.network.hwaddr %s | '
          'cut -d" " -f3' % config_path).strip()
    return None

  def GetNetworkAddress6(self):
    """Gets IPv6 network address of this sandbox.

    >>> s = Sandbox('example')
    >>> s.GetNetworkAddress6()
    'fe80::213:72ff:fedc:7fb4'
    """
    config_path = self._GetConfigPath()
    if self._stub.Exists(config_path):
      output= self._stub.ExecCommand(
          '(ping6 -c 1 -I %s ff02::1 && ip -6 neigh show) | '
          'grep %s | cut -d" " -f1' % (
              self.GetNetworkLinkInterface(),
              self.GetNetworkHwAddress()))
      if output.find('connect: ') == 0:
        return None
      return output.strip()
    return None

  def GetNetworkAddress(self):
    """Gets IPv4 network address of this sandbox.

    >>> s = Sandbox('example')
    >>> s.GetNetworkAddress()
    '192.168.1.1'
    """
    mac_address = self.GetNetworkHwAddress()
    if mac_address:
      lease_path = '/var/lib/misc/dnsmasq*.leases'
      return self._stub.ExecCommand(
          'grep "%s" %s | cut -d" " -f3' % (mac_address, lease_path)).strip()
    return None

  def _GetCgroup(self, sandbox, subsystem):
    system = subsystem.split('.')[0]
    path = '/sys/fs/cgroup/%s/lxc/%s/%s' % (system, sandbox, subsystem)
    if self._stub.Exists(path):
      return self._stub.ExecCommand('cat %s' % path)
    return ''

  def _GetLxcInfo(self, sandbox_id):
    return self._stub.ExecCommand('lxc-info -n %s' % sandbox_id)

  def GetInfo(self):
    """Gets human readable information of this sandbox.

    >>> s = Sandbox('example')
    >>> s.GetInfo() != ''
    True
    """
    infos = []

    for info in [
        self._GetLxcInfo(self.sandbox_id),
        self._GetCgroup(self.sandbox_id, 'memory.stat'),
        self.GetNetworkHwAddress(),
        self.GetNetworkAddress(),
        self.GetNetworkAddress6()
        ]:
      if info:
        infos.append(info)
    return '\n'.join(infos)

  def _SendEvent(self, method, **kwargs):
    response = ips.proto.sandbox_pb2.SendEventResponse()
    try:
      response.description = method(**kwargs)
      response.status = ips.proto.sandbox_pb2.SendEventResponse.SUCCESS
    except ips.utils.CommandExitedWithError, e:
      response.description = str(e)
      response.status = ips.proto.sandbox_pb2.SendEventResponse.FAILED
    return response

  def _SetAcceptRa(self):
    interface = self.GetNetworkLinkInterface()
    if not interface:
      return None

    ra_path = '/proc/sys/net/ipv6/conf/%s/accept_ra' % interface
    val = self._stub.ReadFile(ra_path)
    if val != '2':
      self._stub.ExecCommand('echo 2 > %s' % ra_path)

  def _Start(self):
    """Starts this sandbox.

    >>> s = Sandbox('example')
    >>> s._Start()
    'started'
    """
    self._SetAcceptRa()
    out = self._stub.ExecCommand('lxc-start -d -n %s' % self.sandbox_id)
    statusz_port = self.GetStatuszPort()
    if statusz_port:
      self._OpenNetwork([statusz_port])
    return out

  def _Reboot(self):
    """Reboots this sandbox.

    >>> s = Sandbox('example')
    >>> s._Reboot()
    ''
    """
    return self._stub.ExecCommand('lxc-shutdown -r -n %s' % self.sandbox_id)

  def _Shutdown(self):
    """Shutdowns this sandbox.

    >>> s = Sandbox('example')
    >>> s._Shutdown()
    ''
    """
    out = self._stub.ExecCommand('lxc-shutdown -n %s' % self.sandbox_id)
    out += self._LameduckNetwork(reject_statusz=True)
    return out

  def _Stop(self):
    """Stops this sandbox.

    >>> s = Sandbox('example')
    >>> s._Stop()
    ''
    """
    out = self._stub.ExecCommand('lxc-stop -n %s' % self.sandbox_id)
    out += self._LameduckNetwork(reject_statusz=True)
    return out

  def _Destroy(self):
    """Destroys this sandbox.

    >>> s = Sandbox('example')
    >>> s._Destroy()
    ''
    """
    out = self._stub.ExecCommand('lxc-destroy -n %s' % self.sandbox_id)
    out += self._UnregisterAlternative()
    return out

  def _UnregisterAlternative(self):
    """Unregister alternative for this sandbox.

    >>> s = Sandbox('example')
    >>> s._UnregisterAlternative()
    ''
    """
    proto = self.GetSandboxProto()
    owner = proto.owner.replace('.', '-')

    name = 'ips-sandbox_%s.%s' % (proto.role, owner)
    path = '/var/lib/lxc/%s' % self.sandbox_id

    cmd = 'update-alternatives --remove %s %s' % (name, path)
    return self._stub.ExecCommand(cmd) 

  def _GenDNATRules(self, sandbox_address, port):
    host_address = self._stub.HostAddress()
    rules = []
    rules.append(
        'PREROUTING -t nat -p tcp -d %s --dport %s '
        '-jDNAT --to-destination %s' % (host_address,
                                        port,
                                        sandbox_address))
    rules.append(
        'OUTPUT -t nat -p tcp -d %s --dport %s '
        '-jDNAT --to-destination %s' % (host_address,
                                        port,
                                        sandbox_address))
    return rules

  def _OpenNetwork(self, ports=None):
    """Opens network ports of this sandbox.

    >>> s = Sandbox('example')
    >>> s._OpenNetwork().find('Opened') == 0
    True
    """
    sandbox_address = self.GetNetworkAddress()
    if not sandbox_address:
      return ''

    if ports is None:
      ports = self.GetPorts()
    enabled_ports = dict.fromkeys(self.GetEnabledPorts())

    results = []
    for port in ports:
      if not port in enabled_ports:
        for rule in self._GenDNATRules(sandbox_address, port):
          cmd = '/sbin/iptables -I %s' % rule
          results.append('Opened %s: %s' % (
              rule,
              self._stub.ExecCommand(cmd)))
    return '\n'.join(results)

  def GetEnabledPorts(self):
    """Gets enabled ports of this sandbox.

    >>> s = Sandbox('example')
    >>> s.GetEnabledPorts()
    []
    """
    sandbox_address = self.GetNetworkAddress()
    if not sandbox_address:
      return []

    host_address = self._stub.HostAddress()
    pattern = ('DNAT\W+tcp\W+--\W+%s\W+%s\W+tcp\W+dpt:(\d+)\W+to:%s' % (
        re.escape('0.0.0.0/0'),
        re.escape(host_address),
        re.escape(sandbox_address)))
    rule_re = re.compile(pattern)
    cmd = '/sbin/iptables -L PREROUTING -t nat -n'

    ports = []
    for line in self._stub.ExecCommand(cmd).split('\n'):
      logging.debug('matching %s with rule: %s', line, pattern)
      m = rule_re.match(line)
      if m:
        ports.append(int(m.group(1)))
    return ports

  def _LameduckNetwork(self, reject_statusz=False):
    """Lameducks network ports of this sandbox.

    >>> s = Sandbox('example')
    >>> s._LameduckNetwork()
    ''
    """
    sandbox_address = self.GetNetworkAddress()
    logging.debug('sandbox address is unknown: %s', self.sandbox_id)
    if not sandbox_address:
      return ''

    results = []
    statusz_port = self.GetStatuszPort()
    for port in self.GetEnabledPorts():
      if reject_statusz or statusz_port != port:
        for rule in self._GenDNATRules(sandbox_address, port):
          cmd = '/sbin/iptables -D %s' % rule
          results.append('Closed %s: %s' % (
              rule,
              self._stub.ExecCommand(cmd)))
    return '\n'.join(results)

  def _Provisioning(self, request):
    spec = request.spec.provisioning

    if self._CheckRoleName(spec.role):
      raise InvalidRoleName(spec.role)
 
    if self._CheckOwnerName(spec.owner):
      raise InvalidOwnerName(spec.owner)

    logging.info('creating a new LXC creator for %s', spec.sandbox_id)
    task = _ProvisioningTask(self, spec)
    self._worker.task_queue.put(task)
    return task.progress

  def _Archive(self):
    task = _ArchiveTask(self)
    self._worker.task_queue.put(task)
    return task.progress

  def _GetArchivePath(self):
    return '/var/lib/ips-cell/sandbox/archive/%s.tar.bz2' % self.sandbox_id

  def _GetReadyPort(self):
    ports = self.GetPorts()
    if len(ports) > 0:
      return ports[0]
    return 22

  def IsState(self, state):
    """Returns true if the sandbox is the specified state.

    >>> s = Sandbox('example')
    >>> s.IsState(ips.proto.sandbox_pb2.READY)
    True
    >>> s.IsState(ips.proto.sandbox_pb2.BOOT)
    False
    >>> s.IsState(ips.proto.sandbox_pb2.STOP)
    False
    >>> s.IsState(ips.proto.sandbox_pb2.PROVISIONING)
    False
    >>> s.IsState(ips.proto.sandbox_pb2.ARCHIVING)
    False
    >>> s.IsState(ips.proto.sandbox_pb2.ARCHIVED)
    False
    >>> s.IsState(ips.proto.sandbox_pb2.FAILED)
    False
    >>> s.IsState(ips.proto.sandbox_pb2.NONE)
    False
    """
    if state == ips.proto.sandbox_pb2.READY:
      return self.IsReady()
    elif state == ips.proto.sandbox_pb2.BOOT:
      return self.IsBoot()
    elif state == ips.proto.sandbox_pb2.STOP:
      return self.IsStop()
    elif state == ips.proto.sandbox_pb2.PROVISIONING:
      return self.IsProvisioning()
    elif state == ips.proto.sandbox_pb2.ARCHIVING:
      return self.IsArchiving()
    elif state == ips.proto.sandbox_pb2.ARCHIVED:
      return self.IsArchived()
    elif state == ips.proto.sandbox_pb2.FAILED:
      return self.IsFailed()
    elif state == ips.proto.sandbox_pb2.NONE:
      return self.IsNone()
    return False

  def _IsLxcRunning(self):
    info = self._stub.ExecCommand(
        'lxc-info -n %s | grep state:' % self.sandbox_id)
    return info.split(':')[1].strip() == 'RUNNING'

  def IsReady(self):
    """Returns true if the sandbox is ready to server requests.

    >>> s = Sandbox('example')
    >>> s.IsReady()
    True
    """
    if not self._IsLxcRunning():
      return False

    network_address = self.GetNetworkAddress()

    statusz_port = self.GetStatuszPort()
    if statusz_port:
      return self._HealthByHealthz(network_address, statusz_port)

    return self._HealthByConnect(network_address, self._GetReadyPort())

  def IsBoot(self):
    """Returns true if the sandbox is in boot state.

    >>> s = Sandbox('example')
    >>> s.IsBoot()
    False
    """
    if not self._IsLxcRunning():
      return False

    network_address = self.GetNetworkAddress()

    statusz_port = self.GetStatuszPort()
    if statusz_port:
      return not self._HealthByHealthz(network_address, statusz_port)

    return not self._HealthByConnect(network_address, self._GetReadyPort())

  def IsStop(self):
    """Returns true if the sandbox is in stop state.

    >>> s = Sandbox('example')
    >>> s.IsStop()
    False
    """
    if self._IsLxcRunning():
      return False

    return (
        self._stub.Exists(self._GetConfigPath()) and
        not self._stub.Exists(self._GetArchivePath()) and
        not self.IsArchiving())

  def IsProvisioning(self):
    """Returns true if the sandbox is in provisioning state.

    >>> s = Sandbox('example')
    >>> s.IsProvisioning()
    False
    """
    task = self._worker.task
    return (
        task is not None and
        task.__class__ == _ProvisioningTask and
        task.status == _ProvisioningTask.CREATING)

  def IsArchiving(self):
    """Returns true if the sandbox is in archiving state.

    >>> s = Sandbox('example')
    >>> s.IsArchiving()
    False
    """
    task = self._worker.task
    return (
        task is not None and
        task.__class__ == _ArchiveTask and
        task.status == _ArchiveTask.ARCHIVING)

  def IsArchived(self):
    """Returns true if the sandbox is in archived state.

    >>> s = Sandbox('example')
    >>> s.IsArchived()
    False
    """
    return (
        not self._stub.Exists(self._GetConfigPath()) and
        self._stub.Exists(self._GetArchivePath()))

  def IsFailed(self):
    """Returns true if the sandbox is in failed state.

    >>> s = Sandbox('example')
    >>> s.IsFailed()
    False
    """
    task = self._worker.task
    return (
        task is not None and
        task.__class__ == _ProvisioningTask and
        task.status == _ProvisioningTask.FAILED)

  def IsNone(self):
    """Returns true if the sandbox is in None state.

    >>> s = Sandbox('example')
    >>> s.IsFailed()
    False
    """
    return (
        not self._stub.Exists(self._GetConfigPath()) and
        not self._stub.Exists(self._GetArchivePath()) and
        self._worker.task is None)

  def _HealthByHealthz(self, network_address, port):
    try:
      return self._stub.UrlRead(
          'http://%s:%s/healthz' % (network_address, port)) == 'ok'
    except IOError:
      return False

  def _HealthByConnect(self, network_address, port):
    s = socket.socket()
    try:
      s.connect((network_address, port))
      return True
    except IOError, e:
      return False
    finally:
      s.close()

  def GetState(self):
    """Gets the current state of this sandbox.

    >>> s = Sandbox('example')
    >>> str(s.GetState())
    'state: READY\\n'
    """
    for s in [
        ips.proto.sandbox_pb2.READY,
        ips.proto.sandbox_pb2.BOOT,
        ips.proto.sandbox_pb2.PROVISIONING,
        ips.proto.sandbox_pb2.ARCHIVING,
        ips.proto.sandbox_pb2.ARCHIVED,
        ips.proto.sandbox_pb2.FAILED,
        ips.proto.sandbox_pb2.STOP,
        ips.proto.sandbox_pb2.NONE]:
       if self.IsState(s):
         response = ips.proto.sandbox_pb2.GetStateResponse()
         response.state = s
         if s in (ips.proto.sandbox_pb2.PROVISIONING,
                  ips.proto.sandbox_pb2.ARCHIVING):
           response.description = self._worker.task.progress
         return response

  _ALLOWED_EVENTS = {
    ips.proto.sandbox_pb2.NONE: 
        [ips.proto.sandbox_pb2.SendEventRequest.PROVISIONING],
    ips.proto.sandbox_pb2.PROVISIONING: 
        [],
    ips.proto.sandbox_pb2.FAILED: 
        [ips.proto.sandbox_pb2.SendEventRequest.PROVISIONING,
         ips.proto.sandbox_pb2.SendEventRequest.PROVISIONING],
    ips.proto.sandbox_pb2.STOP: 
        [ips.proto.sandbox_pb2.SendEventRequest.START,
         ips.proto.sandbox_pb2.SendEventRequest.ARCHIVE],
    ips.proto.sandbox_pb2.BOOT: 
        [ips.proto.sandbox_pb2.SendEventRequest.REBOOT,
         ips.proto.sandbox_pb2.SendEventRequest.SHUTDOWN,
         ips.proto.sandbox_pb2.SendEventRequest.LAMEDUCK_NETWORK,
         ips.proto.sandbox_pb2.SendEventRequest.STOP],
    ips.proto.sandbox_pb2.READY: 
        [ips.proto.sandbox_pb2.SendEventRequest.REBOOT,
         ips.proto.sandbox_pb2.SendEventRequest.SHUTDOWN,
         ips.proto.sandbox_pb2.SendEventRequest.OPEN_NETWORK,
         ips.proto.sandbox_pb2.SendEventRequest.LAMEDUCK_NETWORK,
         ips.proto.sandbox_pb2.SendEventRequest.STOP],
    ips.proto.sandbox_pb2.ARCHIVED: 
        [ips.proto.sandbox_pb2.SendEventRequest.DESTROY],
  }

  def GetValidEvents(self):
    """Gets the events which this sandbox can accept with the current state.

    >>> s = Sandbox('example')
    >>> s.GetValidEvents()
    [2, 3, 6, 7, 4]
    """
    state = self.GetState()

    if not state.state in self.__class__._ALLOWED_EVENTS:
      return []
    return self.__class__._ALLOWED_EVENTS[state.state]

  def _CheckValidState(self, event):
    return event in self.GetValidEvents()

  def SendEvent(self, request):
    """Sends an event to this sandbox.

    >>> s = Sandbox('example')
    >>> str(s.GetState())
    'state: READY\\n'

    >>> req = ips.proto.sandbox_pb2.SendEventRequest()
    >>> req.event = ips.proto.sandbox_pb2.SendEventRequest.START
    >>> res = s.SendEvent(req)
    >>> res.status == ips.proto.sandbox_pb2.SendEventResponse.FAILED
    True
    """
    if not self._CheckValidState(request.event):
      response = ips.proto.sandbox_pb2.SendEventResponse()
      response.status = ips.proto.sandbox_pb2.SendEventResponse.FAILED
      response.description = (
          '%s not allowed in the current status.' % GetEventName(request.event))
      return response

    if request.event == request.__class__.START:
      return self._SendEvent(self._Start)
    elif request.event == request.__class__.REBOOT:
      return self._SendEvent(self._Reboot)
    elif request.event == request.__class__.SHUTDOWN:
      return self._SendEvent(self._Shutdown)
    elif request.event == request.__class__.STOP:
      return self._SendEvent(self._Stop)
    elif request.event == request.__class__.DESTROY:
      return self._SendEvent(self._Destroy)
    elif request.event == request.__class__.OPEN_NETWORK:
      return self._SendEvent(self._OpenNetwork)
    elif request.event == request.__class__.LAMEDUCK_NETWORK:
      return self._SendEvent(self._LameduckNetwork)
    elif request.event == request.__class__.ARCHIVE:
      return self._SendEvent(self._Archive)
    elif request.event == request.__class__.PROVISIONING:
      return self._SendEvent(self._Provisioning, request=request)
    return None

  def _CheckRoleName(self, role):
    return role.find('.') != -1 or role.find('-') != -1

  def _CheckOwnerName(self, owner):
    return owner.find('-') != -1

  def GetHelp(self):
    """Gets help message of this sandbox."""
    help_path = '/var/lib/lxc/%s/help' % self.sandbox_id
    if os.path.exists(help_path):
      with open(help_path) as f:
        return f.read()
    return "There's no help for this sandbox: %s" % self.sandbox_id


class _ReadyRootfs:

  def __init__(self, sandbox_id):
    self.sandbox_id = sandbox_id

  def __enter__(self):
    rootfs = None
    for candidate in ['/var/lib/lxc/%s/rootfs' % self.sandbox_id,
                      '/var/lib/lxc/%s/%s/rootfs' % (self.sandbox_id,
                                                     self.sandbox_id)]:
      if os.path.exists(candidate):
        rootfs = candidate
        break
    lvm_rootfs = self._GetLvmRootfs()
    if lvm_rootfs:
      ips.utils.CallExternalCommand('mount %s %s' % (lvm_rootfs, rootfs))
    return rootfs

  def __exit__(self, exc_type, exc_value, traceback):
    lvm_rootfs = self._GetLvmRootfs()
    if lvm_rootfs:
      rootfs = '/var/lib/lxc/%s/rootfs' % self.sandbox_id
      ips.utils.CallExternalCommand('umount %s' % rootfs)
    return False

  def _GetLvmRootfs(self):
    try:
      out = ips.utils.CallExternalCommand(
        'grep lxc.rootfs /var/lib/lxc/%s/config | grep /dev' % (
            self.sandbox_id))
      return out.split(' ')[2].strip()
    except ips.utils.CommandExitedWithError:
      return None

class _ProvisioningTask:

  CREATING = 1
  CREATED = 2
  FAILED = 3

  _Semaphore = threading.Semaphore()

  def __init__(self, sandbox, proto):
    self.proto = proto
    self.sandbox = sandbox
    self.template_name = proto.system
    self.template_options = proto.system_options
    self.version = proto.version
    self.owner = proto.owner
    self.fssize = proto.requirements.disk
    self.ports = proto.requirements.ports

    self.status = _ProvisioningTask.CREATING
    self.progress = 'Waiting'
    self.log = ''
    self.daemon = True

  def _IsLvmAvailable(self):
    return options.sandbox_vgname != ''

  def _IsLvmGuest(self):
    return self.fssize and self.fssize != '-1'

  def _CreateSandbox(self):
    logging.info('Starting provisioing of %s', self.sandbox.sandbox_id)
    extra_options = ''
    if self._IsLvmGuest():
      if not self._IsLvmAvailable():
        self.log = (
          'No storage requirement is supported on this machine. '
          'Check --sandbox_vgname option.')
        self._SetFailed()
        return
      extra_options += ' -B lvm --vgname "%s"' % options.sandbox_vgname
      if self.fssize:
        extra_options += ' --fssize "%s"' % self.fssize
    cmd = 'lxc-create -n "%s" -t "%s" %s' % (self.sandbox.sandbox_id,
                                             self.template_name,
                                             extra_options)
    if self.template_options:
      cmd += ' -- %s' % self.template_options
    try:
      for line in ips.utils.ExternalCommand(cmd):
        self.progress = line
        self.log += line
      self._Cleanup()
    except ips.utils.CommandExitedWithError, err:
      logging.warning(
          'Failed to create sandbox: %s: %s' % (self.sandbox.sandbox_id,
                                                err.out))
      self.log = err.out
      self._SetFailed()
      return
    self._SetCreated()

  def _SetFailed(self):
    self.status = _ProvisioningTask.FAILED
    self.description = self.log

  def _SetCreated(self):
    self._RegisterAlternative()
    path = '/var/lib/lxc/%s/sandbox.proto' % self.sandbox.sandbox_id
    with open('%s.t' % path, 'w') as f:
      f.write(str(self.proto))
    os.rename('%s.t' % path, path)
    self.status = _ProvisioningTask.CREATED

  def _RegisterAlternative(self):
    owner = self.proto.owner.replace('.', '-')

    link = '/var/lib/ips-cell/sandbox/%s/%s.%s' % (owner,
                                                   self.proto.role, owner)
    name = 'ips-sandbox_%s.%s' % (self.proto.role, owner)
    path = '/var/lib/lxc/%s' % self.sandbox.sandbox_id
    priority = int(self.proto.provisioning_time)

    if not os.path.exists(os.path.dirname(link)):
      os.mkdir(os.path.dirname(link))

    cmd = 'update-alternatives --install %s %s %s %d' % (link,
                                                         name, path, priority)
    return ips.utils.CallExternalCommand(cmd) 

  def _Cleanup(self):
    logging.debug('cleaning up:  %s', self.sandbox.sandbox_id)
    self._AddPorts()
    self._AddSharedStorage()
    self._ModifyEtcIssue()
    self._AddDebianChroot()
    self._SetHostname()

  def _AddPorts(self):
    if self.ports:
      sandbox_dir = '/var/lib/lxc/%s' % self.sandbox.sandbox_id
      with open('%s/ports.bak' % sandbox_dir, 'w') as f:
        for port in self.ports:
          f.write('%s\n' % port)
      os.rename('%s/ports.bak' % sandbox_dir, '%s/ports' % sandbox_dir)

  def _SetHostname(self):
    sandbox_dir = '/var/lib/lxc/%s' % self.sandbox.sandbox_id
    logging.debug('modifying /etc/hostname for %s', self.sandbox.sandbox_id)
    hostname = self.sandbox.GetNetworkHwAddress().replace(':', '-')
    with _ReadyRootfs(self.sandbox.sandbox_id) as rootfs:
      with open('%s/etc/hostname' % rootfs, 'w') as f:
        f.write(hostname)
      with open('%s/etc/hosts' % rootfs, 'a') as f:
        f.write('\n127.0.2.1	%s\n' % hostname)

  def _AddSharedStorage(self):
    shared_dir = '%s/%s' % (options.shared_dir, self.proto.owner)
    if not os.path.exists(shared_dir):
      os.mkdir(shared_dir)
      os.chmod(shared_dir, 01777)
    fstab = '/var/lib/lxc/%s/fstab' % self.sandbox.sandbox_id

    # TODO(taruishi) glusterfs bind mount looks terminating the host
    # glusterfs process if you specify -f in umount.
    # This should be fixed to not umount the host it.
    with _ReadyRootfs(self.sandbox.sandbox_id) as rootfs:
      umountfs = '%s/etc/init.d/umountfs' % rootfs
      if os.path.exists(umountfs):
        tmp = '%s/tmp/umountfs.tmp' % rootfs
        ips.utils.CallExternalCommand('/bin/cp %s %s' % (umountfs, tmp))
        ips.utils.CallExternalCommand(
            'sed -e "s/umount -f/umount/" < %s > %s' % (umountfs, tmp))
        os.rename(tmp, umountfs)

    # remove original shared_dir
    cmd = 'grep -v %s %s > %s.t && mv %s.t %s' % (options.shared_dir,
                                                  fstab,
                                                  fstab,
                                                  fstab,
                                                  fstab)
    ips.utils.CallExternalCommand(cmd)

    with open(fstab, 'a') as f:
      f.write('%s mnt none rbind 0 0\n' % shared_dir)

  def _ModifyEtcIssue(self):
    sandbox_dir = '/var/lib/lxc/%s' % self.sandbox.sandbox_id

    logging.debug('modifying /etc/issue for %s', self.sandbox.sandbox_id)
    with _ReadyRootfs(self.sandbox.sandbox_id) as rootfs:
      with open('%s/etc/issue' % rootfs, 'w') as f:
        f.write('%s/%s/%s@%s \\l\n\n' % (self.proto.role,
                                         self.version,
                                         self.owner,
                                         self.sandbox._stub.HostAddress()))

  def _AddDebianChroot(self):
    sandbox_dir = '/var/lib/lxc/%s' % self.sandbox.sandbox_id

    logging.debug('adding /etc/debian_chroot to %s', self.sandbox.sandbox_id)
    with _ReadyRootfs(self.sandbox.sandbox_id) as rootfs:
      with open('%s/etc/debian_chroot' % rootfs, 'w') as f:
        f.write('%s/%s/%s@%s' % (self.proto.role,
                                 self.version,
                                 self.owner,
                                 self.sandbox._stub.HostAddress()))

  def run(self):
    try:
      logging.debug('Acquirng sempahore')
      self.__class__._Semaphore.acquire()
      try:
        self._CreateSandbox()
      finally:
        self.__class__._Semaphore.release()
    except Exception, e:
      logging.warning(
          'Failed to create sandbox: %s: %s' % (self.sandbox.sandbox_id,
                                                str(e)))
      self._SetFailed()


class _ArchiveTask:

  ARCHIVING = 0
  ARCHIVED = 1
  FAILED = 2

  def __init__(self, sandbox):
    self.sandbox = sandbox
    self.status = _ArchiveTask.ARCHIVING
    self.progress = 'Waiting'

  def _Archive(self):
    with _ReadyRootfs(self.sandbox.sandbox_id):
      archive_path = self.sandbox._GetArchivePath()
      cmd = (
          'tar --checkpoint=1000 -jcf %s.$$ -C /var/lib/lxc %s && '
          'mv %s.$$ %s' % (archive_path,
                           self.sandbox.sandbox_id, archive_path, archive_path))
      for line in ips.utils.ExternalCommand(cmd):
        self.progress = line
    self.sandbox._Destroy()
    self.status = _ArchiveTask.ARCHIVED

  def run(self):
    self._Archive()
