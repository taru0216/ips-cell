#!/usr/bin/python

from tornado.options import define, options

import ips.handlers
import ips.server
import os
import sys
import time


define('server', default='localhost:6195')
define('owner', default=os.environ['USER'])
define('role', default='sandbox')
define('remove_stopped_current', default='False')


def GetAlternatives(client):
  method, request = ips.handlers.FormzRpcClient.GetMethodAndRequest(
      'ips_proto_sandbox.SandboxService', 'getAlternatives')
  request.generic_name.owner = options.owner
  request.generic_name.role = options.role
  return client.Call(method, request)


def RemoveUnusedSandbox(client):
  alternatives = GetAlternatives(client)
  for alternative in alternatives.alternatives:
    if IsGarbage(client, alternatives, alternative.sandbox):
      sys.stderr.write(
          'Do you want to remove %s?: [y] ' % alternative.sandbox.sandbox_id)
      inp = sys.stdin.readline().strip().lower()
      if not inp or inp.find('y') == 0:
        RemoveSandbox(client, alternative.sandbox)


def IsGarbage(client, alternatives, sandbox):
  if (options.remove_stopped_current.lower() == 'true' or
      sandbox.sandbox_id != alternatives.current_sandbox_id):
    return not (GetState(client, sandbox).state in (
        ips.proto.sandbox_pb2.READY,
        ips.proto.sandbox_pb2.ARCHIVING,
        ips.proto.sandbox_pb2.ARCHIVED,
        ips.proto.sandbox_pb2.FAILED,
        ips.proto.sandbox_pb2.BOOT))
  return False


def GetState(client, sandbox):
  method, request = ips.handlers.FormzRpcClient.GetMethodAndRequest(
      'ips_proto_sandbox.SandboxService', 'getState')
  request.sandbox_id = sandbox.sandbox_id
  return client.Call(method, request)


def RemoveSandbox(client, sandbox):

  while GetState(client, sandbox).state != ips.proto.sandbox_pb2.STOP:
    time.sleep(1)
  
  method, request = ips.handlers.FormzRpcClient.GetMethodAndRequest(
      'ips_proto_sandbox.SandboxService', 'sendEvent')
  request.sandbox_id = sandbox.sandbox_id
  request.event = ips.proto.sandbox_pb2.SendEventRequest.ARCHIVE
  client.Call(method, request)


def main():
  args = ips.server.ParseOptions()
  client = ips.handlers.FormzRpcClient(options.server)
  RemoveUnusedSandbox(client)


if __name__ == '__main__':
  main()
