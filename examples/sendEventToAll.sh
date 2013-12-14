#!/bin/sh

if test "x$2" = "x"; then
  echo "Usage: $0 <server> <START|REBOOT|SHUTDOWN|STOP>" 1>&2
  exit 1
fi

SERVER=$1
EVENT=$2

ips-rpc-client $SERVER \
    ips_proto_sandbox.SandboxService getSandboxes '' |
        grep sandbox_id: | cut -d' ' -f2 | cut -d'"' -f2 | while read n
do
  echo $SERVER
  echo
  echo $(ips-rpc-client $SERVER \
      ips_proto_sandbox.SandboxService \
          sendEvent "sandbox_id: \"$n\" event: $EVENT" |
              cut -d' ' -f2-)
  echo
  SLEEP=$(echo 100 \* $(wget --no-proxy -O - 'http://localhost:6195/varz?format=raw' 2> /dev/null | grep synchronization-wait-percentage | cut -d: -f2 | cut -d, -f1) + 3 | bc)
  sleep $SLEEP || true
done
