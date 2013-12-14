# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>

__author__    = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'

from ips.proto import variables_pb2
from tornado.options import options, define

import ips.utils

import logging
import os
import re
import subprocess
import threading
import time

define(
    'varz_interval',
    default=30,
    help='interval time to update varz in seconds',
    metavar='SEC')


def _GetCpuSpeed():
  cmd = 'cat /proc/cpuinfo | grep "MHz" | head -1 | cut -d: -f2'
  return int(float(ips.utils.CallExternalCommand(cmd)) * 1000000)


def _GetNumCpus():
  cmd = 'cat /proc/cpuinfo | grep "processor" | wc -l'
  return int(ips.utils.CallExternalCommand(cmd))


def _GetUptime():
  cmd = 'cat /proc/uptime | cut -d" " -f1'
  return float(ips.utils.CallExternalCommand(cmd))


def _GetStartTime(pid=None):
  cmd = 'cat /proc/%d/stat | cut -d" " -f22' % (pid or os.getpid())
  starttime = float(ips.utils.CallExternalCommand(cmd))
  return starttime / int(os.sysconf('SC_CLK_TCK'))


def _GetProcessUptime(pid=None):
  return _GetUptime() - _GetStartTime(pid)


def _GetUptimeAsString():
  cmd = 'uptime'
  return str(ips.utils.CallExternalCommand(cmd)).strip()


def _GetLoadAverage():
  cmd = 'cat /proc/loadavg | cut -d" " -f1'
  return float(ips.utils.CallExternalCommand(cmd))


def _GetUname():
  cmd = 'uname -a'
  return str(ips.utils.CallExternalCommand(cmd)).strip()


def _GetChildrenPids():
  cmd = "ps --ppid %d %d | awk -F' ' '{print $1;}' | grep -v PID" % (
      os.getpid(), os.getpid())
  return ips.utils.CallExternalCommand(cmd).strip().split('\n')


def _GetProcessCpuSeconds(pids=None):
  pids = pids or _GetChildrenPids()
  jiffies = 0
  for pid in pids:
    path = '/proc/%d/stat' % int(pid)
    if os.path.exists(path):
      cmd = 'cat %s | cut -d" " -f14-17' % path
      stat = ips.utils.CallExternalCommand(cmd).split(' ')
      for time in stat:
        jiffies += int(time)
  return jiffies / int(os.sysconf('SC_CLK_TCK'))


class VariableFactory(dict):

  class TopRunner(threading.Thread):

    def __init__(self, factory):
      super(self.__class__, self).__init__()
      self.setDaemon(True)
      self.spliter = re.compile('[ %]+')
      self.factory = factory

    def run(self):
      while True:
        try:
          self._RunTop()
        except Exception, e:
          logging.warning('Failed to run top: %s', str(e))
        time.sleep(self.factory.interval / 2)

    def _RunTop(self):
      top = ips.utils.CallExternalCommand(
          'top -b -n 2 -d %d | grep Cpu | cut -d: -f2- | tail -1' % (
              self.factory.interval / 2))
      vals = self.spliter.split(top)

      # user + sys + nice
      var = self.factory.CreateGaugeVariable(
        'cpu-utilization',
        (float(vals[1]) + float(vals[3]) + float(vals[5])) / 100)
      self.factory[var.key] = var

      # wait
      var = self.factory.CreateGaugeVariable(
        'synchronization-wait-percentage', float(vals[9]) / 100)
      self.factory[var.key] = var

  def __init__(self, interval=None):
    super(self.__class__, self).__init__()
    self.interval = interval or float(options.varz_interval)

    self.thread = threading.Thread(target=self.Run)
    self.thread.daemon = True

    self._GenSystemVariables()

  def Start(self):
    if self.interval > 0:
      self.thread.start()
    else:
      logging.info('Not updating varz periodicallyl since interval is 0')

  def Run(self):
    logging.info('Starting system variable updater')

    top = self.__class__.TopRunner(self)
    top.start()

    while True:
      try:
        self._UpdateVariable()
      except Exception, e:
        logging.warning('Error when getting system variables: %s', str(e))
      time.sleep(self.interval)

  def _UpdateVariable(self):
    self._GenSystemVariables()

    # network
    if 'network-rx-bytes' in self:
      for var in self.CreateNetworkBytesVariables():
        self[var.key] = var

    # disk
    if 'disk-usage' in self:
      for var in self.CreateDiskStatisticsVariables():
        self[var.key] = var

    # memory
    if 'memory-total' in self:
      for var in self.CreateMemoryStatisticsVariables():
        self[var.key] = var

    # packages
    if 'packages' in self:
      var = self.CreatePackagesStatisticsVariable()
      self[var.key] = var

    # netstat
    if 'netstat' in self:
      var = self.CreateNetstatVariable()
      self[var.key] = var

  def CreateCounterVariable(self, key, value=0):
    """Creates Counter Variable.

    >>> f = VariableFactory()
    >>> var = f.CreateCounterVariable('counter')
    >>> print var
    key: "counter"
    type: COUNTER
    Value {
      counter: 0
    }
    <BLANKLINE> 

    >>> var.value.counter = 2
    >>> print var
    key: "counter"
    type: COUNTER
    Value {
      counter: 2
    }
    <BLANKLINE> 
    
    """
    proto = variables_pb2.Variable()
    proto.key = key
    proto.type = variables_pb2.Variable.COUNTER
    proto.value.counter = value
    return proto

  def CreateGaugeVariable(self, key, value=0.0):
    """Creates Integer Variable.

    >>> f = VariableFactory()
    >>> var = f.CreateGaugeVariable('gauge')
    >>> print var
    key: "gauge"
    type: GAUGE
    Value {
      gauge: 0.0
    }
    <BLANKLINE>
    """
    proto = variables_pb2.Variable()
    proto.key = key
    proto.type = variables_pb2.Variable.GAUGE
    proto.value.gauge = value
    return proto

  def CreateStringVariable(self, key, value=''):
    """Creates String Variable.

    >>> f = VariableFactory()
    >>> var = f.CreateStringVariable('counter')
    >>> print var
    key: "counter"
    type: STRING
    Value {
      string: ""
    }
    <BLANKLINE>
    """
    proto = variables_pb2.Variable()
    proto.key = key
    proto.type = variables_pb2.Variable.STRING
    proto.value.string = value
    return proto

  def CreateMapVariable(self,
                        key,
                        columns,
                        type=variables_pb2.Variable.Value.Map.GAUGE,
                        values=None):
    """Creates map variables.

    >>> f = VariableFactory()
    >>> var = f.CreateMapVariable(
    ...     'counter',
    ...     ['interface', 'type'],
    ...     variables_pb2.Variable.Value.Map.COUNTER,
    ...     [('eth0', 'success', 0), ('eth0', 'error', 10)])
    >>> print var
    key: "counter"
    type: MAP
    Value {
      Map {
        columns: "interface"
        columns: "type"
        type: COUNTER
        Value {
          column_names: "eth0"
          column_names: "success"
          counter: 0
        }
        Value {
          column_names: "eth0"
          column_names: "error"
          counter: 10
        }
      }
    }
    <BLANKLINE>
    """
    values = values or {}
    proto = variables_pb2.Variable()
    proto.key = key
    proto.type = variables_pb2.Variable.MAP
    proto.value.map.type = type
    for i in range(len(columns)):
      proto.value.map.columns.append(columns[i])
    for i in range(len(values)):
      value = proto.value.map.value.add()
      for j in range(len(columns)):
        value.column_names.append(values[i][j])
      val = values[i][-1]
      if type == variables_pb2.Variable.Value.Map.GAUGE:
        value.gauge = val
      elif type == variables_pb2.Variable.Value.Map.COUNTER:
        value.counter = val
      else:
        value.string = str(val)
    return proto

  def CreateBuildTimestampVariables(self, timestamp=None):
    """Creates variables containing build-timestamp and build-timestamp-as-int.

    >>> f = VariableFactory()
    >>> import os, time
    >>> os.environ['TZ'] = 'UTC'
    >>> time.tzset()
    >>> timestamps = f.CreateBuildTimestampVariables(0)
    >>> print timestamps['build-timestamp']
    key: "build-timestamp"
    type: STRING
    Value {
      string: "Built at Thu Jan  1 00:00:00 1970 (0)"
    }
    <BLANKLINE>
    >>> print timestamps['build-timestamp-as-int']
    key: "build-timestamp-as-int"
    type: COUNTER
    Value {
      counter: 0
    }
    <BLANKLINE>

    """
    if timestamp != 0:
      timestamp = int(time.time())
    build_timestamp = self.CreateStringVariable('build-timestamp',
        'Built at %s (%d)' % (time.ctime(timestamp), timestamp))
    build_timestamp_as_int = self.CreateCounterVariable(
        'build-timestamp-as-int',
        timestamp)
    return {'build-timestamp': build_timestamp,
            'build-timestamp-as-int': build_timestamp_as_int}

  def CreateNumCpus(self):
    """Creates a variable containing the number of cpus.

    >>> num_cpus = ips.utils.CallExternalCommand(\
        'cat /proc/cpuinfo | grep "processor" | wc -l')

    >>> f = VariableFactory()
    >>> var = f.CreateNumCpus()
    >>> var.value.gauge == int(num_cpus)
    True

    """
    return self.CreateGaugeVariable('num-cpus', _GetNumCpus())

  def CreateCpuSpeed(self):
    """Creates a variable containing the CPU speed.

    >>> f = VariableFactory()
    >>> var = f.CreateCpuSpeed()
    >>> var.key
    'cpu-speed'

    """
    return self.CreateGaugeVariable('cpu-speed', _GetCpuSpeed())

  def CreateUptime(self):
    """Creates a variable containing uptime.

    >>> f = VariableFactory()
    >>> var = f.CreateUptime()
    >>> var.key
    'uptime'

    """
    return self.CreateGaugeVariable('uptime', _GetUptime())

  def CreateStartTime(self):
    """Creates a variable containing starttime.

    >>> f = VariableFactory()
    >>> var = f.CreateStartTime()
    >>> var.key
    'starttime'

    """
    return self.CreateGaugeVariable('starttime', _GetStartTime())

  def CreateCmdline(self):
    """Creates a variable containing cmdline.

    >>> f = VariableFactory()
    >>> var = f.CreateCmdline()
    >>> var.key
    'cmdline'

    """
    cmd = 'cat /proc/%d/cmdline' % os.getpid()
    cmdline = ips.utils.CallExternalCommand(cmd).strip().split('\0')
    return self.CreateStringVariable('cmdline', ' '.join(cmdline))

  def CreateProcessUptime(self):
    """Creates a variable containing process uptime.

    >>> f = VariableFactory()
    >>> var = f.CreateProcessUptime()
    >>> var.key
    'process-uptime'

    """
    return self.CreateGaugeVariable('process-uptime', _GetProcessUptime())

  def CreateUptimeAsString(self):
    """Creates a variable containing uptime as human-readable string

    >>> f = VariableFactory()
    >>> var = f.CreateUptimeAsString()
    >>> var.key
    'uptime-as-string'

    """
    return self.CreateStringVariable('uptime-as-string', _GetUptimeAsString())

  def CreateLoadAverage(self):
    """Creates a variable containing the system load average.

    >>> f = VariableFactory()
    >>> var = f.CreateLoadAverage()
    >>> var.key
    'machine-load-average'

    """
    return self.CreateGaugeVariable('machine-load-average', _GetLoadAverage())

  def CreateProcessCpuSeconds(self, pids=None):
    """Creates a variable containing the elapsed cpu time in second.

    This includes time consumed by child processes.

    >>> f = VariableFactory()
    >>> var = f.CreateProcessCpuSeconds()
    >>> var.key
    'process-cpu-seconds'

    """
    return self.CreateCounterVariable('process-cpu-seconds',
                                      _GetProcessCpuSeconds(pids))

  def CreateTargetProcessCpuSeconds(self, pids_for_targets):
    """Creates a map variable containing the elapsed cpu time in second.

    This includes time consumed by child processes.

    >>> f = VariableFactory()
    >>> pids = {}
    >>> pids['init'] = [1]
    >>> var = f.CreateTargetProcessCpuSeconds(pids)
    >>> var.key
    'target-process-cpu-seconds'

    """
    values = []
    for target in pids_for_targets:
      cpu = _GetProcessCpuSeconds(pids_for_targets[target])
      values.append((target, cpu))
    return self.CreateMapVariable('target-process-cpu-seconds',
                                  ['target'],
                                  type=variables_pb2.Variable.Value.Map.COUNTER,
                                  values=values)

  def CreateUname(self):
    """Creates a variable containing uname.

    >>> f = VariableFactory()
    >>> var = f.CreateUname()
    >>> var.key
    'uname'

    """
    return self.CreateStringVariable('uname', _GetUname())

  def _GetInterfaces(self):
    return ips.utils.CallExternalCommand(
        "ip maddr | grep '^[0-9]' |"
        " awk -F' ' '{print $2;}'").strip().split('\n')

  def _CreateNetworkBytesVariable(self, type):
    column = {'rx': 2, 'tx': 3}[type]
    values = []
    for interface in self._GetInterfaces():
      values.append(
          (interface,
           int(ips.utils.CallExternalCommand(
               'ifconfig "%s" | grep "RX bytes" |'
               ' cut -d":" -f%d | cut -d" " -f1' % (interface,
                                                    column)))))
    val = self.CreateMapVariable(
        'network-%s-bytes' % type,
        ['interface'],
        type=variables_pb2.Variable.Value.Map.COUNTER, values=values)
    return val

  def CreateNetworkBytesVariables(self):
    """Creates variables containing network-rx/tx-bytes."""
    variables = []
    variables.append(self._CreateNetworkBytesVariable('rx'))
    variables.append(self._CreateNetworkBytesVariable('tx'))
    return variables

  def CreateDiskStatisticsVariables(self):
    """Creates variables containing disk usage and size."""
    columns = ['mounted']
    variables = []

    values = {'disk-usage': [], 'disk-size': []}
    cmd = "df | grep / | awk -F' ' '{print $6;}'"

    # usage
    for mounted in ips.utils.CallExternalCommand(cmd).strip().split('\n'):
      cmd = 'df -T -B 1 %s | tail -1' % mounted
      usage = re.split(' +', ips.utils.CallExternalCommand(cmd).strip())
      values['disk-usage'].append((usage[6], int(usage[3])))
      values['disk-size'].append((usage[6], int(usage[2])))

    for var, values in values.iteritems():
      val = self.CreateMapVariable(var, columns, values=values)
      variables.append(val)

    return variables

  def CreateMemoryStatisticsVariables(self):
    """Creates variables containing disk usage and size."""
    variables = []

    mem = re.split(
        ' +',
        ips.utils.CallExternalCommand('free -b | grep Mem:').strip())

    free_cmd_column = ['total', 'used', 'free', 'shared', 'buffers', 'cached']
    for i in range(len(free_cmd_column)):
      val = self.CreateGaugeVariable(
          'memory-%s' % free_cmd_column[i], int(mem[i+1]))
      variables.append(val)

    return variables
  
  def CreateNetstatVariable(self):
    columns = ['prot', 'state']
    values = []

    try:
      cmd = (
          "netstat -ant |"
          "grep -v Foreign |"
          "grep -v 'Active Internet connections' |" 
          "awk -F' ' '{print $6}'"
          )
      states = {}
      for line in ips.utils.ExternalCommand(cmd):
        line = line.strip()
        if not line in states:
          states[line] = 0
        states[line] += 1

      for state, val in states.iteritems():
        values.append(('tcp', state, val))
    except ips.utils.CommandExitedWithError:
      pass

    return self.CreateMapVariable('netstat', columns, values=values)

  def CreatePackagesStatisticsVariable(self):
    columns = ['format', 'name', 'version', 'arch']
    values = []

    # deb
    try:
      cmd = 'dpkg -l 2>&1 | grep "^ii"'
      for line in ips.utils.ExternalCommand(cmd):
        info = re.split(' +', line)
        values.append(('deb', info[1], info[2], info[3], 1))
    except ips.utils.CommandExitedWithError:
      pass

    # rpm
    query_format = '%{Name} %{Version}-%{Release} %{Arch}'
    try:
      for line in ips.utils.ExternalCommand('rpm -qa'):
        for query_line in ips.utils.ExternalCommand(
            'rpm -q --queryformat "%s" %s' % (query_format, line.strip())):
          query = query_line.split(' ')
          values.append(('rpm', query[0], query[1], query[2], 1))
    except ips.utils.CommandExitedWithError:
      pass

    return self.CreateMapVariable('packages', columns, values=values)

  def _GenSystemVariables(self):
    for f in [self.CreateCpuSpeed,
              self.CreateLoadAverage,
              self.CreateNumCpus,
              self.CreateProcessCpuSeconds,
              self.CreateProcessUptime,
              self.CreateCmdline,
              self.CreateStartTime,
              self.CreateUname,
              self.CreateUptime,
              self.CreateUptimeAsString,
             ]:
      var = f()
      self[var.key] = var


if __name__ == "__main__":
  import doctest
  doctest.testmod()
