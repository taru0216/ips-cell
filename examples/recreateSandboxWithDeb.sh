#!/bin/sh

if test "x$4" = "x"; then
  echo "Usage: $0 <new_role> <new_owner> <new_version> <base_sandbox_id>" 1>&2
  exit 1
fi

ROLE=$1
OWNER=$2
VERSION=$3
SANDBOX=$4

ARCHIVE=/var/lib/ips-cell/sandbox/archive/$SANDBOX.tar.bz2

examples/archive2deb.py --archive=$ARCHIVE
sudo dpkg -i ips-sandbox*.deb
http_proxy= ips-update-manager --role=$ROLE --owner=$OWNER --system=ips-archive --system_options="-a /usr/share/ips-cell/sandbox/$ROLE.tar.bz2" --version=$VERSION
/bin/mv ips-sandbox*.deb /org/ips/users/$OWNER
/bin/rm ips-sandbox*
sudo /bin/rm $ARCHIVE
