#!/bin/sh

if test "x$3" = "x"; then
  echo "Usage: $0 <role> <owner> <version> [<base>]" 1>&2
  exit 1
fi

ROLE=$1
OWNER=$2
VERSION=$3

if test "x$4" != "x"; then
  BASE=$4
else
  BASE=$ROLE
fi

http_proxy= ips-update-manager --role=$ROLE --owner=$OWNER --version=$VERSION --system=ips-archive --system_options="-a /usr/share/ips-cell/sandbox/$BASE.tar.bz2" $EXTRA_ARGS
