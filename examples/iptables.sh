#!/bin/sh
#
#  Usage: $0 172.18.167.237 10.0.3.43 '80 443'
#

# GlusterFS ports
# 111: portmap
# 4567: in-house glusterfs-mon server with sinatra
PORTS="111 4567 $(seq 24007 24100) $(seq 38465 38500)"

# PORTS="4567" # sinatra default port

# PORTS="12345 10004" # CloudFoundry DEA

if test "x$2" = "x"; then
  echo "Usage: $0 <host_ip> <guest_ip> [<ports>]" 1>&2
  exit 1
fi

if test "x$3" != "x"; then
PORTS="$3"
fi

HOSTIP=$1
GUESTIP=$2

for p in $PORTS
do 
  echo PREROUTING -t nat -p tcp -d $HOSTIP --dport $p -jDNAT --to-destination $GUESTIP
done

