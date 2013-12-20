# iPS

## Overview

iPS, Induced Pluripotent Stem, is a centralized management system to
deploy, monitor, manage tons of thousands of network nodes called iPS cell
who can host any kind of network services on it.

<pre>
  +-------------+
  | iPS Manager |
  +-------------+
      || Monitor/Manage/Deploy a network service on a iPS cell
      ||
      \/    Tons of thousands of cells
  +----------+
  | iPS cell |-+
  +----------+ |-+
   +-----------+ |
    +------------+
</pre>

iPS Manager and iPS cell can automatically communicate by using zeroconf,
so you don't have to take care of setting up iPS nodes manually. The manager
recognizes the life-cycle of iPS cell correctly and then manages it to 
host a network servie on it.

The manager and cells have integratred web-based consoles to highly control
themselves, including higher level RPCs to control things, medium level
interfaces such as modifying files and calling shell commands, and lower
level web-based terminal emulator which enables you to login the system
only with your browser, that is, you can monitor the node statistics
with top, vmstat, iostat by using only the browser.

<pre>
 +------------------------------------------------+   +== Applications
 |High level RPCs / Integrated Form for RPCs      | &lt;=+ 
 +------------------------------------------------+        +-------+
 |Integrated Management tools to monitor, login   | &lt;===== |Browser|
 +------------------------------------------------+        |       |
 |Integrated Terminal Emulator                    | &lt;===== +-------+
 +------------------------------------------------+
</pre>
