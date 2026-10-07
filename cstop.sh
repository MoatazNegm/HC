#!/bin/sh
# cstop.sh -- CONTAINER flavour only.  Called by the node container's entrypoint when the container gets a normal
# stop (docker stop, docker restart, host shutdown), BEFORE anything is torn down.
#
# All node containers of the dev cluster share one kernel.  A node that stops with its pool still imported leaves
# the pool in the kernel with its disks gone: a SUSPENDED pool, and on ZFS 2.4.4 a command that waits for a
# transaction group on such a pool (export, reguid ...) holds ZFS's global lock for ever -- every zpool / zfs
# command on the host then hangs until the host is rebooted (2026-10-07, twice).  So a clean stop hands the pools
# over first: every pool this node owns that is ONLINE is exported while its disks still answer.  The cluster then
# does what it does for any lost node (the leader assigns the pool, the survivor imports it and moves the cache to
# itself).  A kill / power loss cannot run this; that case is /pace/closthost.sh on the survivor.
#
# Never "zpool export -a" (that would take the other nodes' pools too) and never "-f".
me=`hostname`
log() { echo "`date '+%H:%M:%S'` cstop $me: $*" >> /root/cstop.log; }
log "stop requested"
for p in `/pace/cpoolowner.sh mine $me`; do
	st=`cat /proc/spl/kstat/zfs/$p/state 2>/dev/null`
	if [ "$st" != "ONLINE" ]; then
		log "pool $p is $st -- not touched"
		continue
	fi
	# the disks must answer before anything that waits for them is started
	vdev=`zpool status -P $p 2>/dev/null | awk '$1 ~ /^\/dev\//{print $1; exit}'`
	if [ -n "$vdev" ] && ! timeout 10 dd if=`readlink -f $vdev` of=/dev/null bs=4k count=1 iflag=direct 2>/dev/null; then
		log "pool $p: its disks do not answer -- not exported"
		continue
	fi
	if timeout 100 zpool export $p >> /root/cstop.log 2>&1; then
		log "pool $p exported"
	else
		log "pool $p: export refused or timed out (busy?) -- left imported"
	fi
done
log "done"
exit 0
