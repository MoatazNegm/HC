#!/usr/bin/bash
# closthost.sh <lost host>  -- CONTAINER flavour only (called by hostlost.sh when is_container).
#
# When a physical server dies, everything it held dies with it: its iSCSI target, the pools it had imported.
# A container that dies leaves all of that behind in the kernel it shared with the other nodes:
#   - its LIO target and backstores stay configured (and keep the shared loop disks claimed, so no other node
#     can export them),
#   - its pools stay "imported", with vdevs that no longer answer (the pool suspends).
# This script puts the surviving node where a physical one would be:
#   1. removes the lost host's iSCSI target, its backstores and the dead sessions to it;
#   2. waits until this node exports the shared disks itself and sees them again (caddtargetdisks.sh and
#      iscsiwatchdog.sh do that on their own; the disks keep their serial = their SCSI id, see caddtargetdisks.sh);
#   3. resumes the pools of the lost host (zpool clear) and exports them cleanly.
# After that the pool is simply "not imported anywhere", and the normal path takes over, the same as on physical
# servers: the leader names a node (poolnxt), that node imports the pool (zpooltoimport.py) and gives it a local cache.
lost=$1
[ -z "$lost" ] && exit 0
log() { echo "`date '+%H:%M:%S'` closthost $lost: $*" >> /root/closthost.log; }
exec 9>/tmp/closthost.lock
flock -n 9 || { log "another run is in progress"; exit 0; }
log "start"
# pools of the lost host, read before anything is touched
orphans=`/pace/cpoolowner.sh mine $lost`
log "its pools: ${orphans:-none}"
# 1. the target side it left behind
if targetcli ls /iscsi 2>/dev/null | grep -q "iqn.2016-03.com.$lost:t1"; then
	timeout 60 targetcli /iscsi delete iqn.2016-03.com.$lost:t1 >/dev/null 2>&1
	log "target removed"
fi
for bs in `targetcli ls /backstores/block 2>/dev/null | awk '/o- .*-'$lost' /{print $3}'`; do
	timeout 30 targetcli /backstores/block delete $bs >/dev/null 2>&1
done
log "backstores left for $lost: `targetcli ls /backstores/block 2>/dev/null | grep -c -- "-$lost "`"
# the initiator side: the sessions to the dead target would only end after the replacement timeout
timeout 20 iscsiadm -m node -T iqn.2016-03.com.$lost:t1 -u >/dev/null 2>&1
timeout 10 iscsiadm -m node -T iqn.2016-03.com.$lost:t1 -o delete >/dev/null 2>&1
[ -z "$orphans" ] && { log "no pool to hand over"; exit 0; }
# 2. wait for the disks of every orphan pool to answer again (through this node's own export)
for p in $orphans; do
	n=0
	while [ $n -lt 90 ]; do
		/pace/cdiskids.sh
		missing=0
		for v in `zpool status -P $p 2>/dev/null | awk '$1 ~ /^\/dev\//{print $1}'`; do
			[ -b "`readlink -f $v`" ] || missing=$((missing+1))
		done
		[ $missing -eq 0 ] && break
		sleep 2; n=$((n+2))
	done
	log "pool $p: disks back after ${n}s (missing=$missing)"
	# 3. resume and export
	timeout 60 zpool clear $p >/dev/null 2>&1
	sleep 1
	if timeout 120 zpool export $p >> /root/closthost.log 2>&1; then
		log "pool $p exported -- it can be imported by the node the leader names"
	else
		timeout 60 zpool clear $p >/dev/null 2>&1
		timeout 120 zpool export -f $p >> /root/closthost.log 2>&1 && log "pool $p exported (second try)" || log "pool $p could NOT be exported"
	fi
done
log "done"
exit 0
