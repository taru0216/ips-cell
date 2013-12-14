#!/usr/bin/python
#
# Copyright (c) 2013 Masato Taruishi <taru0216@gmail.com>
#


__authour__   = "Masato Taruishi"
__copyright__ = "Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>"


from tornado.options import define, options

import ips.handlers
import ips.utils
import ips.variable_factory
import logging
import os.path
import sys
import tornado.ioloop
import tornado.options


define(
    'varz_network',
    default=None,
    metavar='true|false',
    help='Adds network statistics varz')

define(
    'varz_disk',
    default=None,
    metavar='true|false',
    help='Adds disk usage statistics varz')

define(
    'varz_memory',
    default=None,
    metavar='true|false',
    help='Adds memory usage statistics varz')

define(
    'varz_packages',
    default=None,
    metavar='true|false',
    help='Adds package statistics varz')

define(
    'varz_netstat',
    default=None,
    metavar='true|false',
    help='Adds netstat varz')

define(
    'enable_devz',
    default='false',
    metavar='true|false',
    help='Enables /devz/ interface')


def InitVariables():
  """Initializes and returns common variables for iPS servers."""
  ParseOptions()
  f = ips.variable_factory.VariableFactory()

  # timestamp
  timestamp = ReadTimestamp()
  for name, var in f.CreateBuildTimestampVariables(timestamp).iteritems():
    f[name] = var

  # network
  if options.varz_network:
    for var in f.CreateNetworkBytesVariables():
      f[var.key] = var

  # disk
  if options.varz_disk:
    for var in f.CreateDiskStatisticsVariables():
      f[var.key] = var

  # memory
  if options.varz_memory:
    for var in f.CreateMemoryStatisticsVariables():
      f[var.key] = var

  # packages
  if options.varz_packages:
    var = f.CreatePackagesStatisticsVariable()
    f[var.key] = var

  # netstat
  if options.varz_netstat:
    var = f.CreateNetstatVariable()
    f[var.key] = var

  f.Start()
  return f


def ReadTimestamp():
  """Reads buildinfo file and returns build-timestamp value."""
  buildinfo = ips.utils.GetDataFile('buildinfo')
  if os.path.exists(buildinfo):
    with open(buildinfo) as f:
      for line in f:
        if line.split(':')[0] == 'build-timestamp':
          return int(line.split(':')[1].strip())
  return 0


def InitWebHandlers(service, variables=None, statusz=None):
  """Initializes and returns common web handers for iPS server."""
  variables = variables or InitVariables()
  handlers = [
    (r"/healthz", ips.handlers.HealthzHandler, dict(service=service)),
    (r"/varz", ips.handlers.VarzHandler, dict(vars=variables)),
    (r"/quitquitquit", ips.handlers.QuitHandler),
  ]
  if statusz:
    handlers.append(ips.handlers.StatuszHandler, dict(service=service))
  if options.enable_devz == 'true':
    handlers.append((r"/devz/(.*)", ips.handlers.DevzHandler))
  return handlers 


def ServerLoop(port, handlers):
  app = tornado.web.Application(handlers)
  logging.info('Listening %d', port)
  app.listen(port)

  tornado.ioloop.IOLoop.instance().start()

_parsed_args = None

def ParseOptions():
  """Parses command line options."""
  global _parsed_args
  if _parsed_args is None:
    _parsed_args = tornado.options.parse_command_line()
    logging.info('Starting %s', sys.argv[0])
  return _parsed_args
