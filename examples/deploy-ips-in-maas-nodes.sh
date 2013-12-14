#!/bin/sh

if test "x$2" = "x"; then
  echo "Usage: $0 <profile> <apt-repository for iPS>" 1>&2
  echo "    e.g: $0 ips 'deb http://server/ips/ ./'" 1>&2
  exit
fi

PROFILE="$1"
DEB="$2"

for_each_host() {
  maas-cli $PROFILE nodes list | grep hostname | cut -d'"' -f4 |
      cut -d. -f1
}

for_each_host | while read h
do
  echo -n "Installing iPS into $h... "
  if test "x$(wget -O - http://$h.local:6195/healthz 2> /dev/null)" = "xok"; then
    echo "already installed"
  else
    ssh -o 'StrictHostKeyChecking no' -lubuntu "$h.local" "
        sudo sh -c \
            'echo $DEB > /etc/apt/sources.list.d/ips.list &&
                apt-get update &&
                apt-get -y --force-yes -o APT::Install-Recommends=0 install \
                    ips-cell'
        " < /dev/null 1>&2
    echo "done"
  fi
done
