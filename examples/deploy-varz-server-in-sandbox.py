#!/usr/bin/python


import pexpect
import sys


ip = sys.argv[1]
port = int(sys.argv[2])


child = pexpect.spawn(
    '/usr/bin/ssh',
    [
        '-o',
        'StrictHostKeyChecking=no',
        '-lubuntu',
        '-t',
        ip,
        """sudo sh -c "
cat > /etc/init/ips.conf <<EOF
start on runlevel [2345]
stop on runlevel [016]

respawn

exec python -c 'import threading; import ips.tools; import ips.server; ips.tools.options.port=\\\"%d\\\"; ips.server.options.varz_packages=\\\"true\\\"; ips.tools.StartTool(threading.Thread())'

EOF
initctl reload-configuration
service ips start
\"
""" % port,
    ],
)
child.expect('password: ', timeout=120)
child.sendline('ubuntu')
child.expect('password for ubuntu: ')
child.sendline('ubuntu')
child.expect(pexpect.EOF)
print child.before
