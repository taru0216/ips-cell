#!/bin/sh


SERVER=localhost:6195
SERVICE=ips_proto_sandbox.SandboxService
ROLE=sandbox
#OWNER=$(whoami)
OWNER=masato.taruishi

getState() {
  sandbox=$1
  ips-rpc-client $SERVER $SERVICE getState "sandbox_id: \"$1\"" | cut -d' ' -f2
}

getCurrent() {
  ips-rpc-client $SERVER $SERVICE getAlternatives "generic_name { owner: \"$OWNER\" role: \"$ROLE\"}" | grep current | cut -d'"' -f2
}

sendEvent() {
  sandbox=$1
  event=$2
  expected_state=$3

  echo -n "Sending $event to $sandbox..." 1>&2
    ips-rpc-client $SERVER $SERVICE sendEvent "sandbox_id: \"$sandbox\" event: $event" > /dev/null
    while test "x$(getState $sandbox)" != "x$expected_state";
    do
      echo -n "." 1>&2
      sleep 1
    done
    echo " done" 1>&2
}

stop_sandbox() {
  sandbox=$1
  if test "x$(getState $sandbox)" != "xSTOP"; then
    sendEvent $sandbox SHUTDOWN STOP
  fi
}

getAlternatives() {
  ips-rpc-client $SERVER $SERVICE getAlternatives "generic_name { owner: \"$OWNER\" role: \"$ROLE\"}" | grep ' sandbox_id' | cut -d'"' -f2
}

stop_all_alternatives() {
  for sandbox in $(getAlternatives);
  do
    stop_sandbox $sandbox
  done
}

start_current() {
  sendEvent $(getCurrent) START READY
}

open_current() {
  sendEvent $(getCurrent) OPEN_NETWORK READY
}

sudo /usr/sbin/update-alternatives --config ips-sandbox_$ROLE.$(echo $OWNER | tr '.' '-')

current_state=$(getState $(getCurrent))

case "$current_state" in
  STOP)
    stop_all_alternatives
    start_current
    ;;
esac

open_current
echo "$(getCurrent): $(getState $(getCurrent))"
