#!/usr/bin/python
#
# Copyright (c) 2013 Masato Taruishi <taru0216@gmail.com>
#

"""sandbox_service.py: manages sandbox."""

__authour__   = "Masato Taruishi"
__copyright__ = "Copyright (c) 2013 Masato Taruishi <taru0216@gmail.com>"


import ips.proto.sandbox_pb2
import ips.sandbox
import logging
import os


class Error(Exception):
  pass


class LxcSandboxService(ips.proto.sandbox_pb2.SandboxService):

  def __init__(self):
    """Initilizes SandboxService using lxc.

    This service implements SandboxService RPC service using lxc as
    its backend.
    """
    super(LxcSandboxService, self).__init__()
    self.sandboxes = {}

    self.manager_service = None

  def GetSandboxes(self):

    candidates = {}

    # gets candidates from lxc-ls result
    cmd = 'lxc-ls | grep -v RUNNING | grep -v FROZEN | grep -v STOPPED'
    cmd += '| grep -v "^$"'
    try:
      for candidate in ips.utils.ExternalCommand(cmd):
        candidates[candidate.strip()] = True
    except ips.utils.CommandExitedWithError:
      pass

    cmd = "find /var/lib/ips-cell/sandbox/archive/ -name '*.tar.bz2'"
    for archive in ips.utils.ExternalCommand(cmd):
      sandbox = '.'.join(os.path.basename(archive).split('.')[:-2])
      candidates[sandbox] = True

    logging.debug('collected sandbox candidates: %s' % candidates.keys())
    return sorted(candidates.keys())

  def GetSandboxProtoForGenericName(self, generic_name):
    path = '/var/lib/ips-cell/sandbox/%s.%s/sandbox.proto' % (
        generic_name.role, generic_name.owner)
    return self._GetSandboxProto(path)

  def getSandboxes(self, controller, request, done=None):
    response = ips.proto.sandbox_pb2.GetSandboxesResponse()
    for sandbox in self.GetSandboxes():
      response.sandbox_id.append(sandbox)
    if done:
      done.run(response)
    else:
      return response

  def getGenericNames(self, controller, request, done=None):
    response = ips.sandbox.Alternatives.GetGenericNames()
    if done:
      done.run(response)
    else:
      return response

  def setAlternative(self, controller, request, done=None):
    alternatives = ips.sandbox.Alternatives(request.generic_name)
    response = alternatives.SetAlternative(request.sandbox_id)
    if done:
      done.run(response)
    else:
      return response

  def getAlternatives(self, controller, request, done=None):
    alternatives = ips.sandbox.Alternatives(request.generic_name)
    response = alternatives.GetAlternatives()
    if done:
      done.run(response)
    else:
      return response

  def _GetStatus(self):
    return ips.utils.CallExternalCommand('lxc-list')

  def getStatus(self, controller, request, done=None):
    response = ips.proto.sandbox_pb2.GetStatusResponse()
    response.status = self._GetStatus()
    if done:
      done.run(response)
    else:
      return response

  def GetAvailableSandboxes(self):
    ids = []
    for sandbox_id in self.GetSandboxes():
      if self.GetSandbox(sandbox_id).GetState().state in [
        ips.proto.sandbox_pb2.STOP,
        ips.proto.sandbox_pb2.BOOT,
        ips.proto.sandbox_pb2.READY,
      ]:
        ids.append(sandbox_id)
    return ids

  def GetSandbox(self, sandbox_id):
    if not sandbox_id in self.sandboxes:
      self.sandboxes[sandbox_id] = ips.sandbox.Sandbox(sandbox_id)
    return self.sandboxes[sandbox_id]

  def getInfo(self, controller, request, done=None):
    response = ips.proto.sandbox_pb2.GetInfoResponse()
    response.info = self.GetSandbox(request.sandbox_id).GetInfo()
    if done:
      done.run(response)
    else:
      return response

  def getState(self, controller, request, done=None):
    response = self.GetSandbox(request.sandbox_id).GetState()
    if done:
      done.run(response)
    else:
      return response

  def sendEvent(self, controller, request, done=None):
    response = self.GetSandbox(request.sandbox_id).SendEvent(request)
    if done:
      done.run(response)
    else:
      return response
