#


def GetService(service):
  """Gets service class for the specified service name.

  >>> GetService('ips_proto_manager.ManagerService')
  <class 'manager_pb2.ManagerService'>
  """
  proto_package = service.split('.')[0]
  python_module = proto_package.replace('_', '.') + '_pb2'
  m = __import__(python_module, fromlist=[None])
  return getattr(m, service.split('.')[1])


if __name__ == '__main__':
  import doctest
  doctest.testmod()
