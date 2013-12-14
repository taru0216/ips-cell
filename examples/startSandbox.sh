#!/bin/sh

id=$1

sendEvent() {
  event=$1
  ips-rpc-client localhost:6195 ips_proto_sandbox.SandboxService sendEvent "sandbox_id: \"$id\" event: $event"
}

getState() {
  ips-rpc-client localhost:6195 ips_proto_sandbox.SandboxService getState "sandbox_id: \"$id\""
}

sendEvent START

echo -n "Waiting for the state of $id to be READY..." 1>&2
for i in `seq 1 5`; do
  echo -n "." 1>&2
  if test "$(getState)" = "state: READY"; then
    echo "done" 1>&2
    sendEvent OPEN_NETWORK
    exit 0
  fi
  sleep $i
done

echo -n "Failed to make the state of $id READY: " 1>&2
getState 1>&2
exit 1
