#!/bin/sh

server=localhost:6195
ips-rpc-client $server \
    ips_proto_sandbox.SandboxService getSandboxes '' |
        grep sandbox_id: | cut -d' ' -f2 | cut -d'"' -f2 | while read n
do
  echo $server:$n
  echo $(ips-rpc-client $server \
      ips_proto_sandbox.SandboxService getState "sandbox_id: \"$n\"" |
          cut -d' ' -f2-)
done
