# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>

__author__ = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


import doctest
import ips.variable_factory
import unittest

def suite():
  suite = unittest.TestSuite()
  suite.addTests(doctest.DocTestSuite(ips.variable_factory))
  return suite
