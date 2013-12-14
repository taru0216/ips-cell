# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>


__author__ = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


import handlers_test
import sandbox_test
import unittest
import variable_factory_test


def all_suite():
  suite = unittest.TestSuite()
  suite.addTests(handlers_test.suite())
  suite.addTests(sandbox_test.suite())
  suite.addTests(variable_factory_test.suite())
  return suite
