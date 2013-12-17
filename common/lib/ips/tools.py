#!/usr/bin/env python


__author__    = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


from tornado.options import define, options

import ips.server
import logging
import os
import random
import socket
import sys
import threading
import time
import tornado.ioloop


define('port', default=None, help='tcp port to listen', metavar='PORT')


def StartTool(thread, handlers=None):
  ips.server.ParseOptions()

  service = os.path.basename(sys.argv[0])

  handlers = handlers or ips.server.InitWebHandlers(service)

  thread.start()

  port = int(options.port or random.randint(10000, 60000))
  logging.info(
      'Starting %s at http://%s:%s/', service, socket.gethostname(), port)
  ips.server.ServerLoop(port, handlers)
  logging.info('Exiting')


def StopTool():
  tornado.ioloop.IOLoop.instance().stop()
