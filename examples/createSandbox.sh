#!/bin/sh

CELL=localhost
PROTO=""
OWNER=`whoami`
ROLE=sandbox
SYSTEM=ubuntu
VERSION=12.04
PORTS=
FSSIZE=-1
OPTIONS="-r precise"
COMMENT=

get() {
  local help="$1"
  local default="$2"

  echo -n "$help [$2]: " 1>&2
  read buf
  if test "x$buf" = "x"; then
    echo $default
  else
    echo $buf
  fi
}

TIME=$(date +%s)

ports() {
  echo "$PORTS" | grep [0-9] | tr ' ' '\n' | while read port
  do
    echo ports: $port
  done
}

CELL=$(get 'CELL' "$CELL")
OWNER=$(get 'OWNER' "$OWNER")
ROLE=$(get 'ROLE' "$ROLE")
SYSTEM=$(get 'SYSTEM' "$SYSTEM")
VERSION=$(get 'VERSION' "$VERSION")

if test "x$NAME" = "x"; then
  NAME=$TIME
  NAME=$NAME.$(echo $VERSION | tr . -)
  NAME=$NAME.$(echo $ROLE | tr . -)
  NAME=$NAME.$(echo $OWNER | tr . -)
fi

NAME=$(get 'NAME' "$NAME")
PORTS=$(get 'PORTS' "$PORTS")
FSSIZE=$(get 'FSSIZE' "$FSSIZE")
OPTIONS=$(get 'OPTIONS' "$OPTIONS")
COMMENT=$(get 'COMMENT' '')



CONFIRM=$(get "Are you sure you want to create?: $NAME", 'yes')

if test "x$CONFIRM" != "xyes"; then
  exit 1
fi

PROTO="
sandbox_id: \"$NAME\"
event: PROVISIONING
Spec {
  provisioning {
    sandbox_id: \"$NAME\"
    owner: \"$OWNER\"
    role: \"$ROLE\"
    version: \"$VERSION\"
    system: \"$SYSTEM\"
    system_options: \"$OPTIONS\"
    provisioning_time: $TIME
    comment: \"$COMMENT\"
    Requirements {
      disk: \"$FSSIZE\"
      $(ports)
    }
  }
}
"

SERVER=$CELL:6195
echo "Creating $NAME..."
ips-rpc-client $SERVER ips_proto_sandbox.SandboxService sendEvent "$PROTO"
