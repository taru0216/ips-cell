# Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>

"""
Common tornado request handlers for iPS.

This module consists of a set of request handlers which
can be used with iPS servers. All iPS servers have /varz,
/healthz and /quitquitquit endpoints, which provides system
information and availability. In addition, /devz/ interface
provides a lot of useful features including login console,
file read / write page, and shell executions.

 # handlers
 handlers = [
     (r"/healthz", ips.handlers.HealthzHandler, dict(service=service)),
     (r"/varz", ips.handlers.VarzHandler, dict(vars=variables)),
     (r"/quitquitquit", ips.handlers.QuitHandler),
 ]

 # create a web server instance which has the above endpoints.
 app = tornado.web.Application(handlers)

"""

__author__    = 'Masato Taruishi'
__copyright__ = 'Copyright (c) 2013, Masato Taruishi <taru0216@gmail.com>'


from ips.proto.variables_pb2 import Variable
from tornado.options import options

import ips.sandbox
import ips.utils

import google.protobuf.service
import google.protobuf.text_format
import logging
import os
import os.path
import random
import re
import socket
import subprocess
import tempfile
import threading
import time
import tornado.web
import urllib


class HealthzHandler(tornado.web.RequestHandler):
  """Handles requests for /healthz endpoint.

  This handler returns 'ok' if the request has the service argument same as
  this service name, or 'NG' if the service argument is different from this
  service. Typically, this is used to check whether the service is working
  correctly. A health checker sends a get request to
  'http://<somewhere:someport>/healthz/service=<exptected_service>' to check
  whether the service 'expected_service' is working in <somewhere>:<someport>.
 
  If the checker gets 'NG' from the URL, then it recognizes the service isn't
  working properly at <somewhere>:<someport>. The typical way to register
  this handler is as follows:

    (r"/healthz", HealthzHandler, dict(service='my_service'))
  """

  def initialize(self, service=None):
    """Initializes with the specified service name."""
    self.service = service

  def IsHealth(self):
    """Check whether the service is healthy.

    Returns True if the service is available.
    """
    service = self.get_argument('service', None)
    if self.service is None or service is None or self.service == service:
      return True
    else:
      return False

  def get(self):
    """Handles GET requests."""
    if self.IsHealth():
      self.write('ok')
    else:
      self.write('NG')


class VarzHandler(tornado.web.RequestHandler):
  """Handles requests for /varz endpoint.

  This handler returns a list of variables of this service. The format
  of this list is as follows:

    <key1>: <val1>
    <key2>: map:<col1>:<col2>.. <col1_key>:<col2_key>:<val>

  Examples:

    cpu-speed: 200000000
    network-rx-bytes: map:interface eth0:11111 eth1:100

  Typical way to register this handler is as follows:

    (r"/varz", VarzHandler, dict(vars=variables))
  """

  def initialize(self, vars):
    """Initializes with the specified list of variables."""
    self.vars = vars

  def get(self):
    """Handles GET requests."""
    format = self.get_argument('format', 'json')
    if format == 'raw':
      self._WritePlain()
    elif format == 'json':
      self._WriteJson()

  def _WritePlain(self):
    content_type = 'text/plain'
    self.set_header('Content-Type', content_type)
    for name, var in self.vars.iteritems():
      self.write('%s: %s\n' % (name, self._GetValue(var, content_type)))

  def _WriteJson(self):
    import json
    content_type = 'application/json'
    self.set_header('Content-Type', content_type)
    varz = {}
    for name, var in self.vars.iteritems():
      varz[name] = self._GetValue(var, content_type) 
    self.write(json.dumps(varz, indent=True, sort_keys=True))

  def _AddMapValue(self, root, type, map_value):
    node = root
    for column in map_value.column_names:
      if not column in node:
        node[column] = {}
      node = node[column]
    if type == Variable.Value.Map.GAUGE:
      node['gauge'] = map_value.gauge
    elif type == Variable.Value.Map.COUNTER:
      node['counter'] = map_value.counter
    elif type == Variable.Value.Map.STRING:
      node['string'] = map_value.string

  def _GetValue(self, var, content_type):
    if var.type == Variable.GAUGE:
      return var.value.gauge
    elif var.type == Variable.COUNTER:
      return var.value.counter
    elif var.type == Variable.STRING:
      return var.value.string
    elif var.type == Variable.MAP:
      if content_type == 'application/json':
        columns = [column for column in var.value.map.columns]
        values = {}
        for map_value in var.value.map.value:
          self._AddMapValue(values, var.value.map.type, map_value)
        return {
            'columns': columns,
            'values': values}
      else:
        columns = 'map:' + ':'.join(var.value.map.columns)
        type = 'string'
        if var.value.map.type == Variable.Value.Map.GAUGE:
          type = 'gauge'
        if var.value.map.type == Variable.Value.Map.COUNTER:
          type = 'counter'
        vals = [
            ':'.join(val.column_names) +
            ':%d' % getattr(val, type) for val in var.value.map.value]
        return columns + ' %s' % ' '.join(vals)


class StatuszHandler(tornado.web.RequestHandler):
  """General /statusz endpoint.

  This class implements an endpoint for iPS /statusz. You can
  use this handler to show your general system information,
  and also you can inherite this class to provide your own
  system information by overwriting WriteCommonStatusHeader(),
  GenStatusz() method.

  /statusz is separeted into 2 parts called HEADER, MAIN.
  Write your header part in WriteCommonStatusHeader(), and
  main part in GenStatusz().

    <HEADER PART>
    <MAIN PART>
  """

  InitTimestamp = time.time()

  def initialize(self, service):
    """Initializes the handler."""
    self.service = service

  def get(self):
    """Handles GET request."""
    self.write('<body style="background: #eeeeee;">')
    self.WriteCommonStatusHeader()
    self.write(self.GenStatusz())
    self.write('</body>')

  def WriteCommonStatusHeader(self):
    """Writes your header part of the /statusz endpoint.

    This method writes the header part
    """
    self.write('<h2>Status of %s</h2>' % self.service)
    start = self.__class__.InitTimestamp
    self.write(
        'Start at %s (%d seconds ago)</pre>' % (time.ctime(start),
                                                time.time() - start))
    self.write('<pre>%s</pre>' % self.__class__._GetLsbRelease())
    self.write('<h3>Memory</h3>')
    self.write('<pre>%s</pre>' % self.__class__._GetFree())
    self.write('<h3>Disk</h3>')
    self.write('<pre>%s</pre>' % self.__class__._GetDF())

  def GenStatusz(self):
    """Generates main content of your statusz endpoint."""
    return ''

  @classmethod
  def _GetLsbRelease(cls):
    return ips.utils.CallExternalCommand('lsb_release -a')

  @classmethod
  def _GetFree(cls):
    return ips.utils.CallExternalCommand('free')

  @classmethod
  def _GetDF(cls):
    return ips.utils.CallExternalCommand('df || true')


class HelpzHandler(tornado.web.RequestHandler):
  """Handles request for /helpz endpoint.

  This handler returns usage of this service.

    (r"/helpz", HelpzHandler, dict(usage=USAGE))
  """
  def initialize(self, usage):
    self.usage = usage

  def get(self):
    if self.usage:
      self.write(self.usage)
      self.finish()


class FormzRpcClient:
  """Client for FormzHandler.

  This class implements a RPC client which talks to FormzHandler.
  """

  def __init__(self, host):
    """Instantiates a RPC client for the specified host.

    >>> FormzRpcClient('server')
    >>> FormzRpcClient('192.168.1.1')
    >>> FormzRpcClient('192.168.1.1:6195')
    >>> FormzRpcClient('[fe80::1]:6195')
    """
    self.host = host

  def Call(self, method, request):
    """Calls the RPC for the specified method descriptor with request."""

    # check if the request is correctly initialized, this throws
    # message.EncodeError
    request.SerializeToString()

    service = method.containing_service.full_name
    url = 'http://%s/formz/%s/%s' % (self.host, service,
                                     method.name)
    params = urllib.urlencode({'text_proto': str(request)})
    logging.debug('sending rpc with a request %s to %s', str(params), url)
    f = urllib.urlopen(url, params)
    try:
      if f.getcode() != 200:
        raise google.protobuf.service.RpcException('RPC returned error: %d',
            f.getcode())
      response_text = f.read()
      logging.debug('got rpc response %s from %s', response_text.strip(), url)
      response = ips.proto.GetService(service).GetResponseClass(method)()
      google.protobuf.text_format.Merge(response_text, response)
      return response
    finally:
      f.close()

  @classmethod
  def GetMethodAndRequest(cls, service_name, method_name):
    """Gets the method and the request argument.

    >>> FormzRpcClient.GetMethodAndRequest(
        'ips_proto_manager.ManagerService', 'getCells')
    """
    service = ips.proto.GetService(service_name)
    method = service.GetDescriptor().FindMethodByName(method_name)
    argument = service.GetRequestClass(method)()
    return method, argument


class FormzHandler(tornado.web.RequestHandler):
  """Handles requests for /formz/ endpoint.

  This handler parses protobuf RPCs and generate HTML form
  to make users call RPCs from their browser.
  """

  def initialize(self, service_protos):
    """Initializes with the specified service_protos.

    Args:
      service_protos: list of protobuf service implementations
    """
    self.service_protos = {}
    for service in service_protos:
      name = service.GetDescriptor().full_name
      logging.debug('Registering %s form handler', name)
      self.service_protos[name] = service

  def get(self, service, method):
    """Handles GET requests.

    This handles HTTP GET request for /formz/.

      /formz/<RPC service>/<method>

    It lists a list of methods which the service has, if you don't
    specify <method> as /formz/<service>/

    It lists a web page which you can submit a request argument
    for the method if you specify <service> as well. The form
    is sent to the same URL with POST HTTP method.

    Args:
      service: RPC service name
      method: RPC method name
    """
    if self._GetService(service) and method in self._GetMethodNames(service):
      self.write('<h1>RPC %s</h1>' % self._GetMethod(service, method).full_name)
      path = self._GetServiceFilePath(service)
      self.write(
          '<a href="/devz/file?path=%s&format=raw">See definition</a>' % path)
      self.write('<h2>Argument %s</h2>' %
          self._GetMethod(service, method).input_type.name)
      self.write(
          '<form method=post>'
          '  <textarea name=text_proto rows=25 cols=80>%s</textarea><br>'
          '  <input type=submit>'
          '</form>' % self.get_argument('text_proto',''))
      self.finish()
    elif self._GetService(service) and not method:
      self.write('<h1>Service %s</h1>' %
          self._GetService(service).GetDescriptor().full_name)
      for name in self._GetMethodNames(service):
        self.write('<li><a href="%s">%s</a>' % (name, name))
      self.finish()
    else:
      self.set_status(404)
      self.finish()

  def _GetMethodNames(self, service):
    return [m.name for m in self._GetService(service).GetDescriptor().methods]

  def _GetService(self, service):
    if service in self.service_protos:
      return self.service_protos[service]
    return None

  def _GetMethod(self, service, name):
    for m in self._GetService(service).GetDescriptor().methods:
      if m.name == name:
        return m
    return None

  def _GetServiceFilePath(self, service):
    path = self._GetService(service).GetDescriptor().file.name
    return ips.utils.GetDataFile(path)

  def post(self, service, method):
    """Handles HTTP POST requests.

    This calls a RPC method with the specified request argument
    provided by 'text_proto' query.
    """
    if self._GetService(service) and method in self._GetMethodNames(service):
      try:
        request = self._ParseTextProto(service, method,
                                       self.get_argument('text_proto', ''))
        logging.debug('got request: %s', str(request))
        response = getattr(self._GetService(service), method)(None, request)
        self._WriteResponse(response, self.get_argument('format',
                                                        'text/plain'))
        self.finish()
      except (google.protobuf.text_format.ParseError,
              google.protobuf.message.DecodeError) as e:
        self.set_status(400)
        self.write(str(e))
        self.finish()
    else:
      self.set_status(404)
      self.finish()

  def _ParseTextProto(self, service, method, text_proto):
    text_proto = self.get_argument('text_proto', '')
    request = self._GetService(service).GetRequestClass(
        self._GetMethod(service, method))()
    google.protobuf.text_format.Merge(text_proto, request)
    return request

  def _WriteResponse(self, proto, content_type):
    self.set_header('Content-Type', content_type)
    if content_type == 'application/x-protobuf':
      self.write(proto)
    else:
      self.set_header('Content-Type', 'text/plain')
      self.write(google.protobuf.text_format.MessageToString(proto,
                                                             as_utf8=True))


class Terminal:
  """Provides terminal in your browser.

  This class implements a terminal for your shell command to
  make it possible to use in your browser by executing ajaxterm
  in a different thread.

  See Console class how to integrate this terminal with iPS.
  """

  HTML = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html>
<head>
	<title>%s</title>
	<meta http-equiv="content-type" content="text/html; charset=UTF-8"/>
	<link rel="stylesheet" type="text/css" href="ajaxterm.css"/>
	<script type="text/javascript" src="sarissa.js"></script>
	<script type="text/javascript" src="sarissa_dhtml.js"></script>
	<script type="text/javascript" src="ajaxterm.js"></script>
	<script type="text/javascript" src="ajaxterm_config.js"></script>
	<script type="text/javascript" src="utf8-escape.js"></script>
	<script type="text/javascript">
	window.onload=function() {
		t=ajaxterm.Terminal("term",width,height);
	};
	</script>
</head>
<body>
<div id="term"></div>
</body>
</html>
  """

  def __init__(self, name, command):
    self.name = name
    self.command = command
    self.port = random.randint(10000, 60000)
    self.index_html = tempfile.mktemp()
    self.cmd = None
    self.thread = None

  def Start(self):
    """Starts the terminal.

    This executes the terminal in a different thread
    with a random port. You can use 'port' variable
    of this instance what port the terminal is listening.
    """
    if not self.IsAlive():
      self.thread = threading.Thread(target=self._Run)
      self.thread.daemon = True
      self.thread.start()

  def Stop(self):
    """Stops the terminal.

    This stops the terminal if it's running. Nothing
    happens if the terminal has been already stopped.
    """
    if self.IsAlive():
      logging.info('killing cmd: %s', self.cmd)
      os.unlink(self.index_html)
      self.cmd.Kill()
      logging.info('joining terminal thread')
      self.thread.join()
    self.thread = None

  def IsAlive(self):
    """Returns True if the terminal is running."""
    if self.thread:
      return self.thread.isAlive()
    return False

  def _Run(self):
    while True:
      with open(self.index_html, 'w') as f:
        f.write(Terminal.HTML % self.name)
      self.cmd = ips.utils.ExternalCommand(
          'exec /usr/bin/ajaxterm -l -p %d -c "%s" -i %s -T 300'
          % (self.port, self.command, self.index_html))

      for line in self.cmd:
        logging.debug('message from ajaxterm: %s', line)

      if self.cmd.retval != 0:
        time.sleep(1)
        logging.warning('cmd: %s exited: %d', self.cmd.cmd, self.cmd.retval)


class Proxy:
  """Forwards HTTP requests to a designated server.

  This class implements a simple server to forward HTTP
  requests to a different server. You can use this as a simple
  HTTP proxy server and especially for ajaxterm to make it
  available from external clients without any server software
  such as apache.

  See Console class how to integrate this with iPS.
  """

  def __init__(self, host, port):
    self.host = host
    self.port = port

  def _HandleResponse(self, handler, response): 
    if response.error and not isinstance(response.error,
                                         tornado.httpclient.HTTPError):
      logging.info("response has error %s", response.error) 
      handler.set_status(500) 
      handler.write("Internal server error:\n" + 
                 str(response.error)) 
      handler.finish() 
    else: 
      handler.set_status(response.code) 
      for header in ("Date", "Cache-Control", "Set-Cookie",
                     "Server", "Content-Type", "Location"):
        v = response.headers.get(header) 
        if v: 
          handler.set_header(header, v) 
      if response.body: 
        handler.write(response.body) 
      handler.finish() 

  def Proxy(self, handler):
    """Forwards HTTP requests to the designated server.

    This forwards the contents of RequestHandler instance
    to the designated server. The request is retried several
    times if the server doesn't respond. This might be a
    problem if the request is not idempotent. So please
    use other implementations if it's not acceptable for you
    requirements.
    """
    body = handler.request.body
    if body == '':
      body = None
    for i in range(3):
      try:
        request = tornado.httpclient.HTTPRequest(
            url="http://%s:%s%s" % (self.host, self.port, handler.request.uri),
            method=handler.request.method,
            body=body,
            headers=handler.request.headers,
            follow_redirects=False)
        logging.debug('forwarding %s', request.url)
        response = tornado.httpclient.HTTPClient().fetch(request)
        self._HandleResponse(handler, response)
        return
      except tornado.httpclient.HTTPError, x: 
        logging.debug("tornado signalled HTTPError %s", x) 
        if hasattr(x, 'response') and x.response:
          if x.response.status_code != 599 and i != 4: 
            self._HandleResponse(handler, x.response)
            return
          else:
            raise x
        logging.debug('waiting 0.5 sec to retry proxy')
        time.sleep(0.5)
    raise tornado.httpclient.HTTPError(
        503, 'too many retry to %s:%s' % (self.host, self.port))


class QuitHandler(tornado.web.RequestHandler):
  """Terminates your server.

  This class implements the endpoint to make your server shutdown.
  You can easily terminate your server by accessing
  /quitquitquit?confirm=yes. If you don't specify confirm=yes,
  then a confirmation page will be displayed to check if the
  access is actually intended.
  """

  def _Terminate(self):
    time.sleep(3)
    logging.warning('exiting by quitquitquit')
    os._exit(0)

  def get(self):
    """Handles GET request."""
    if self.get_argument('confirm', None):
      self.write('will quit in 3 seconds')
      thread = threading.Thread(target=self._Terminate)
      thread.daemon = True
      thread.start()
      self.finish()
    else:
      self.write('<h1>Terminating "%s"</h1>' % options.name)
      self.write('<p>Are you sure you want to quit?</p>')
      self.write(
          '<form><input type=hidden name=confirm value=yes>'
          '<input type=submit value=yes></form>')
      self.finish()


class DevMethods:
  """Method interface for /devz/(.*) endpoints.

  This class provides the general method for /devz/(.*)
  endpoints. You can easily create your own /devz/ method
  by using this interface.
  """

  def Get(self, handler, unused_match):
    """Handles GET requests.

    It just returns Method Not Allowed 405 http response code.
    You should implement your own dev method and overwrite this.
    """
    handler.set_status(405)
    handler.finish()

  def Post(self, handler, unused_match):
    """Handles POST requests.

    It just returns Method Not Allowed 405 http response code.
    You should implement your own dev method and overwrite this.
    """
    handler.set_status(405)
    handler.finish()


class Shell(DevMethods):
  """Executes one-line shell script.

  This class implements an endpoint to execute one-line shell
  script and show the output in your brower. For example, you
  can get a lit of packages in the system as follows:

    /devz/sh?cmd=dpkg -l
  """

  def Get(self, handler, unused_match):
    """Handles GET requests."""
    cmd = handler.get_argument('cmd', None)
    if cmd:
      output = None
      try:
        output = ips.utils.CallExternalCommand(cmd)
      except ips.utils.CommandExitedWithError, e:
        handler.write('<b>%s exited with an error: %d</b><br>' % (e.cmd,
                                                                  e.retval))
        output = e.out
      handler.write('<pre>%s</pre>' % output)
    handler.write(
        '<form method=post><input type=text value="%s" ' % cmd +
        'id=cmd name=cmd></form>')
    handler.finish()

  def Post(self, handler, unused_match):
    """Handles POST requests."""
    cmd = handler.get_argument('cmd', None)
    if not cmd:
      handler.redirect('')
    output = None
    try:
      output = ips.utils.CallExternalCommand(cmd)
    except ips.utils.CommandExitedWithError, e:
      handler.write('<b>%s exited with an error: %d</b>' % (e.cmd, e.retval))
      output = e.out
    handler.write('<pre>%s</pre>' % output)
    handler.write(
        '<form method=post><input type=text id=cmd value="%s" ' % cmd +
        'name=cmd></form>')
    handler.finish()


class File(DevMethods):
  """File Read / Write endpoint.

  This endpoint implements a way to write and read files in your
  system. You can see the raw file as follows:

    /devz/file?path=/etc/motd&format=raw

  If you don't specify format and the mime-type of the file starts
  with text, then a simple text area is used to make it possible to
  edit the file. Also, you can upload files by accessing directories.

    /devz/file?path=/tmp/
  """

  def _IsHumanReadable(self, path):
    mime_type = ips.utils.CallExternalCommand(
        'file --mime-type %s | cut -d: -f2' % path).strip()
    if mime_type:
      return mime_type.find('text/') == 0 or mime_type == 'application/xml'
    return False

  def _ReadRaw(self, handler, path):
    mime_type = ips.utils.CallExternalCommand(
        'file --mime-type %s | cut -d: -f2' % path).strip()
    if mime_type:
      handler.set_header('Content-Type', mime_type)
    with open(path) as f:
      if self._IsHumanReadable(path) and handler.get_argument('q', None):
        pattern = re.compile(handler.get_argument('q'))
        for line in f:
          if pattern.search(line):
            handler.write(line)
      else:
        handler.write(f.read())

  def Get(self, handler, unused_match):
    """Handles GET request."""
    path = handler.get_argument('path')
    format = handler.get_argument('format', None)
    if format == 'raw':
      if not os.path.exists(path):
        handler.set_status(404)
        handler.finish()
        return
      if os.path.isdir(path):
        handler.set_status(403)
        handler.finish()
        return
      self._ReadRaw(handler, path)
    else:
      buf = ''
      handler.write('<h1>%s</h1>' % path)
      handler.write('<h2>Attibutes</h2>')
      mime_type = 'text/plain'
      if os.path.exists(path):
        mime_type = ips.utils.CallExternalCommand(
            'file --mime-type %s | cut -d: -f2' % path).strip()
        output = ips.utils.CallExternalCommand('/bin/ls -l %s' % path)
        if mime_type != 'inode/directory':
          with open(path) as f:
            buf = f.read()
        handler.write('<pre>%s</pre>' % output.strip())
      else:
        handler.write('<p>new file</p>')

      handler.write('<pre>%s</pre>' % mime_type)

      if self._IsHumanReadable(path):
        handler.write('<form method=post>')
        handler.write(
            '<textarea rows=25 cols=80 name=c>%s</textarea><br>' % buf)
        handler.write('<input type=submit>')
        handler.write('</form>')
      elif mime_type == 'inode/directory':
        handler.write('<form enctype="multipart/form-data" method=post>')
        handler.write('File: <input type="file" name="file1" />')
        handler.write('<input type=submit>')
        handler.write('</form>')
    handler.finish()

  def Post(self, handler, unused_match):
    """Handles POST request."""
    path = handler.get_argument('path')
    tmp = '%s.t' % path
    buf = ''

    if not os.path.isdir(path):
      if os.path.exists(path):
        ips.utils.CallExternalCommand('/bin/cp %s %s' % (path, tmp))
      buf = handler.get_argument('c', '')
    else:
      file1 = handler.request.files['file1'][0]
      tmp = '%s/%s' % (path, file1['filename'])
      buf = file1['body']

    with open(tmp, 'w') as f:
      f.write(buf)

    if not os.path.isdir(path):
      os.rename(tmp, path)
      
    handler.redirect('?%s' % urllib.urlencode({'path': path}))


class Console(DevMethods):
  """Console method for devz interface

  This class implements web-based text terminals including
  logging in the iPS server, seeing syslog, top and vmstat,
  and opening iPS sandbox virtual terminals at the following
  endpoints:

   /devz/console/login/
   /devz/console/root/
   /devz/console/syslog/
   /devz/console/vmstat/
   /devz/console/top/
   /devz/console/sandbox/<sandbox_id>/
   /devz/console/ssh/<sandbox_id>/
  """

  _Terminals = None

  @classmethod
  def _InitTerminals(cls):
    Console._Terminals = {
        'root': Terminal(name='login : %s' % options.name,
                          command='sudo /bin/login -f root'),
        'login': Terminal(name='login : %s' % options.name,
                          command='sudo /bin/login'),
        'syslog': Terminal(name='syslog : %s' % options.name,
                           command='/usr/bin/tail -f /var/log/syslog'),
        'cell-log': Terminal(name='log (cell) : %s' % options.name,
                             command='/usr/bin/tail -f /var/log/ips-cell.log'),
        'manager-log': Terminal(
            name='log (manager) : %s' % options.name,
            command='/usr/bin/tail -f /var/log/ips-manager.log'),
        'top': Terminal(name='top : %s' % options.name,
                        command='/bin/su nobody -c /usr/bin/top'),
        'vmstat': Terminal(name='vmstat : %s' % options.name,
                           command='/usr/bin/vmstat 1'),
    }

  def _Handle(self, handler, match):
    command = match.group(1)
    endpoint, terminal = self._GetTerminal(handler, command)
    if terminal:
      if not terminal.IsAlive():
        terminal.Start()
      try:
        endpoint.Proxy(handler)
      except tornado.httpclient.HTTPError, e:
        terminal.Stop()
        handler.set_status(503)
    else:
      handler.set_status(404)
      handler.finish()

  def Get(self, handler, match):
    """Handles GET request."""
    self._Handle(handler, match)

  def Post(self, handler, match):
    """Handles POST request."""
    self._Handle(handler, match)

  def _GetTerminal(self, handler, command):
    if not Console._Terminals:
      Console._InitTerminals()

    # returns pre-defined terminal
    if command in Console._Terminals:
      terminal = Console._Terminals[command]
      return Proxy('localhost', terminal.port), terminal

    # returns sandbox terminal
    if command.find('sandbox/') == 0:
      sandbox_id = command.split('/')[1]
      sandbox = ips.sandbox.Sandbox(sandbox_id)
      proto = sandbox.GetSandboxProto()
      terminal = Terminal(
          name='%s %s (%s)' % (proto.role, proto.version, proto.owner),
          command='exec lxc-console -e "/" -n %s 2> /dev/null' % sandbox_id)
      Console._Terminals[command] = terminal
      terminal.Start()
      return Proxy('localhost', terminal.port), terminal

    # returns sandbox ssh
    if command.find('ssh/') == 0:
      sandbox_id = command.split('/')[1]
      sandbox = ips.sandbox.Sandbox(sandbox_id)
      user = command.split('/')[2]
      cmd = (
          'exec ssh'
          ' -l %s'
          ' -o UserKnownHostsFile=/dev/null'
          ' -o StrictHostKeyChecking=no'
          ' %s' % (user,
                   sandbox.GetNetworkAddress()))
      proto = sandbox.GetSandboxProto()
      terminal = Terminal(name='%s %s (%s)' % (proto.role,
                                               proto.version,
                                               proto.owner), command=cmd)
      Console._Terminals[command] = terminal
      terminal.Start()
      return Proxy('localhost', terminal.port), terminal

    return None, None


class Mon(DevMethods):
  """Handles /devz/mon/ endpoint.

  /devz/mon/ endpoint provides a simple page to consist of
  a set of monitoring consoles such as top, vmstat and
  syslog.
  """

  def Get(self, handler, unused_match):
    """Handles GET request."""
    handler.write(
        '<html><head>'
        '  <title>Monitor Console %s </title>'
        '  <style type="text/css">'
        '  iframe { width: 640; height: 400; }'
        '  </style>'
        '</head><body>' % options.name)
    handler.write(
        '<div id=top>\n'
        '  <h3>Top</h3>\n'
        '  <iframe src="/devz/console/top/" scrolling=no></iframe>\n'
        '</div>')
    handler.write(
        '<div id=vmstat>\n'
        '  <h3>Vmstat</h3>\n'
        '  <iframe src="/devz/console/vmstat/" scrolling=no></iframe>\n'
        '</div>')
    handler.write(
        '<div id=syslog>\n'
        '  <h3>Syslog</h3>\n'
        '  <iframe src="/devz/console/syslog/" scrolling=no></iframe>\n'
        '</div>')
    handler.write(
        '</body></html>')
    handler.finish()


class DevzHandler(tornado.web.RequestHandler):
  """Handles requests for /devz endpoint.

  /devz is used to develope rapidly. This provides useful information
  to develop rapidly.
  """

  _Methods = {
      'console/(.+)/': Console(),
      'file': File(),
      'mon': Mon(),
      'sh': Shell(),
  }

  def get(self, method):
    """Handles GET request."""
    for pattern in DevzHandler._Methods:
      m = re.match(pattern, method)
      if m:
        return DevzHandler._Methods[pattern].Get(self, m)
    self.write('not found')
    self.set_status(404) 
    self.finish()

  def post(self, method):
    """Handles POST request."""
    for pattern in DevzHandler._Methods:
      m = re.match(pattern, method)
      if m:
        return DevzHandler._Methods[pattern].Post(self, m)
    self.write('not found')
    self.set_status(404) 
    self.finish()
