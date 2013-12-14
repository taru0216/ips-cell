# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>

__author__ = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


class Flag:
  """Flag of iPS.

  Flag of iPS is a value which can have a default value and it's mutable.

  >>> f = Flag('my_flag')
  >>> f.Get()
  >>> f.Set(True)
  >>> f.Get()
  True

  >>> f = Flag('my_flag', True)
  >>> f.Get()
  True
  """

  def __init__(self, name, default=None):
    self.name = name
    self.value = None
    self.default = default

  def Get(self):
    """Gets the value of this flag."""
    if self.value is None:
      return self.default
    return self.value

  def Set(self, value):
    """Sets the value of this flag to the specified value."""
    self.value = value

if __name__ == '__main__':
  import doctest
  doctest.testmod()
