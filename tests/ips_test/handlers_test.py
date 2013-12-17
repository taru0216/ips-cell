# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>


__author__ = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


import tornado.options

import ips.handlers
import ips.sandbox_service
import ips.server
import json
import sys
import tornado.testing
import tornado.web
import traceback
import unittest


tornado.options.parse_command_line(args=[None])


class HealthzTest(tornado.testing.AsyncHTTPTestCase):

  def get_app(self):
    return tornado.web.Application(
        [(r'/healthz', ips.handlers.HealthzHandler, dict(service='test'))])

  def test_should_return_ok(self):
    self.http_client.fetch(self.get_url('/healthz'), self.stop)
    res = self.wait()
    self.assertIn("ok", res.body)

  def test_should_return_ok_for_appropriate_service(self):
    self.http_client.fetch(self.get_url('/healthz?service=test'), self.stop)
    res = self.wait()
    self.assertIn("ok", res.body)

  def test_should_return_NG_for_different_service(self):
    self.http_client.fetch(self.get_url('/healthz?service=no'), self.stop)
    res = self.wait()
    self.assertIn("NG", res.body)


class VarzTest(tornado.testing.AsyncHTTPTestCase):

  def setUp(self):
    errors = []
    for i in range(5):
      try:
        super(self.__class__, self).setUp()
        return
      except Exception, e:
        # the tornado testcase sometimes throws an exception to try opening
        # a socket in use.
        errors.append((e, traceback.format_exc()))
    raise Exception("Could not setup testscase: %s" % errors)

  def get_app(self):
    vars = ips.server.InitVariables()
    return tornado.web.Application(
        [(r'/varz', ips.handlers.VarzHandler, dict(vars=vars))])

  def test_should_return_varz_as_json(self):
    self.http_client.fetch(self.get_url('/varz'), self.stop)
    res = self.wait()
    varz = json.loads(res.body)
    self.assertIn("process-cpu-seconds", varz)

    self.http_client.fetch(self.get_url('/varz?format=json'), self.stop)
    res = self.wait()
    varz = json.loads(res.body)
    self.assertIn("process-cpu-seconds", varz)

  def test_should_return_varz_as_raw(self):
    self.http_client.fetch(self.get_url('/varz?format=raw'), self.stop)
    res = self.wait()
    with self.assertRaises(ValueError):
      varz = json.loads(res.body)
    self.assertIn("process-cpu-seconds: ", res.body)


class StatuszTest(tornado.testing.AsyncHTTPTestCase):

  def get_app(self):
    return tornado.web.Application(
        [(r'/statusz', ips.handlers.StatuszHandler, dict(service='test'))])

  def test_should_return_memory_statistics_section(self):
    self.http_client.fetch(self.get_url('/statusz'), self.stop)
    res = self.wait()
    self.assertIn("<h3>Memory</h3>", res.body)


class HelpzTest(tornado.testing.AsyncHTTPTestCase):

  def get_app(self):
    return tornado.web.Application(
        [(r'/helpz', ips.handlers.HelpzHandler, dict(usage='usage'))])

  def test_should_return_usage(self):
    self.http_client.fetch(self.get_url('/helpz'), self.stop)
    res = self.wait()
    self.assertIn("usage", res.body)


class FormzTest(tornado.testing.AsyncHTTPTestCase):

  def get_app(self):
    services = [ips.sandbox_service.LxcSandboxService()]
    return tornado.web.Application(
        [(r'/formz/(.*)/(.*)',
          ips.handlers.FormzHandler, dict(service_protos=services))])

  def test_should_return_a_list_of_methods(self):
    self.http_client.fetch(
        self.get_url('/formz/ips_proto_sandbox.SandboxService/'), self.stop)
    res = self.wait()
    self.assertIn("getSandboxes", res.body)

  def test_should_return_a_form_for_rpc(self):
    self.http_client.fetch(
        self.get_url('/formz/ips_proto_sandbox.SandboxService/getSandboxes'),
        self.stop)
    res = self.wait()
    self.assertIn("textarea", res.body)


def suite():
  suite = unittest.TestSuite()
  suite.addTests(unittest.makeSuite(HealthzTest))
  suite.addTests(unittest.makeSuite(VarzTest))
  suite.addTests(unittest.makeSuite(StatuszTest))
  suite.addTests(unittest.makeSuite(HelpzTest))
  suite.addTests(unittest.makeSuite(FormzTest))
  return suite
