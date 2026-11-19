#!/bin/sh
# ciscsirelease.sh -- CONTAINER flavour only (called by cstop.sh before it exports the pools of this node).
# An iSCSI volume is a zvol that the LIO target uses as a block backstore (zdN-<host>-<volume>, addzfsvolumeastarget.sh).
# As long as the backstore holds the zvol open, 'zpool export' answers "pool is busy", so a clean stop of a node with
# iSCSI volumes left its pool imported (and the stop then suspended it).  The backstores of this host's zvols are removed
# here (their LUNs and ACL mappings go with them); the new owner of the pool builds them again from the volume list
# (VolumeCheck.py -> iscsi.py) once it has imported the pool.
me=`hostname`
for bs in `targetcli ls /backstores/block 2>/dev/null | sed -n 's/.*o- \(zd[0-9]*-'$me'-[^ ]*\) .*/\1/p'`
do
	timeout 30 targetcli /backstores/block delete $bs >/dev/null 2>&1 && echo "`date '+%H:%M:%S'` ciscsirelease $me: backstore $bs removed" >> /root/cstop.log
done
# The LIO configuration is ONE for all the node containers (shared kernel), but the listening socket of a portal belongs to
# the network namespace of the node that created it: when this node is gone the target still shows "Portals OK" while
# nothing listens ("Connection refused"), and the new owner's 'create portal' answers "already exists".  So the data
# targets whose portal address is on this node (iqn.2016-03.com.<ip without dots>:data, not the :t1 disk targets, not other
# nodes' addresses) are removed too; the new owner builds them again.
for t in `targetcli ls /iscsi 2>/dev/null | sed -n 's/.*o- \(iqn\.2016-03\.com\.[0-9]*:data\) .*/\1/p'`
do
	pip=`targetcli ls /iscsi/$t/tpg1/portals 2>/dev/null | sed -n 's/.*o- \([0-9.]*\):[0-9]* .*/\1/p' | head -1`
	[ -n "$pip" ] || continue
	ip -4 -o addr 2>/dev/null | grep -q " $pip/" || continue
	# QSD5.352 r10q (QC proof 10p F8, 554.1/554.2): the stop runs twice (stopnode's cstop, then docker stop's).  Between the
	# two runs the partner imported the pool and built the target of the address again (its own backstores zdN-<partner>-..)
	# while this node still had the address up: the second run (zfs1 19:12:26) deleted the partner's NEW target 4 s after it
	# was made (zfs2 19:12:22), q550c's ACL failed and .153 stayed without a target.  A target that maps a backstore of
	# another node is that node's now: it is kept and logged.
	other=`timeout 20 targetcli ls /iscsi/$t/tpg1/luns 2>/dev/null | grep -o 'block/[^ ]*' | sed 's/^block\///' | grep -v -- "-$me-" | head -1`
	if [ -n "$other" ]; then
		echo "`date '+%H:%M:%S'` ciscsirelease $me: target $t kept: it maps $other of another node (r10q F8)" >> /root/cstop.log
		continue
	fi
	timeout 30 targetcli /iscsi delete $t >/dev/null 2>&1 && echo "`date '+%H:%M:%S'` ciscsirelease $me: target $t removed" >> /root/cstop.log
done
timeout 30 targetcli saveconfig >/dev/null 2>&1
exit 0
