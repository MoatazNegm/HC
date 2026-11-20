#!/bin/bash
# hostalive.sh <host> [<node ip>|-] [<etcd ip for the ready list>|-] [<rounds>]
# QSD5.352 r10r2 (QC proof r10r, candidate A), container flavour: is <host> still alive?
#   exit 0 = it answers (alive), 1 = it does not answer (or its address is now another host's), 2 = no address known
# One line with the reason on stdout.  Used before every destructive step of the host-lost path: heartbeat.py (own etcd
# unreadable), leaderlost.sh (take-over), hostlost.sh (sysfs delete of its disks) and closthost.sh (its target, backstores,
# pool export).  In r10r a follower whose OWN etcd stalled took the live leader for lost 32 times in a row: it took the
# cluster ip, deleted the leader's SCSI devices from the shared kernel and removed its iSCSI target (3 pools DEGRADED).
# The address of <host> is, in this order: the given node ip, the portal of its iSCSI target iqn.2016-03.com.<host>:t1
# (in the kernel the containers share; a dead container leaves it there, but its address no longer answers), its
# ready/<host> record.  An address on this node itself (the cluster ip after a take-over) is never taken.
# Alive = ping or TCP 2379 answers on that address in one of <rounds> rounds (2 s apart) and the etcd there does not name
# another host (an address that a returned/rebuilt node uses now, under a new host name, is not the lost host).
# r10r3 (validator r10r2 V-1, V-3, V-4): (1) 'the ready list gives the address to another host' is NOT alive only when
# ready/<host> itself is missing or has another address; listed for <host> AND another host (a stale record of an earlier
# build with the same ip) is ambiguous and answers ALIVE: no destructive step on an unclear identity.  (2) targetcli is
# read only when no usable node ip is given (it reads the whole LIO tree, up to 20 s, on every genuine take-over).
# (3) 0.0.0.0 and 127.* are never taken (targetcli's default portal answers ping locally: a false ALIVE).
host=$1; nip=$2; eip=$3; rounds=${4:-1}
[ -z "$host" ] && { echo "hostalive: no host"; exit 2; }
[ "$nip" = "-" ] && nip=''
[ "$eip" = "-" ] && eip=''
nip=${nip%%/*}; eip=${eip%%/*}
et() { ETCDCTL_API=3 timeout ${HOSTALIVE_ETCDTMO:-4} etcdctl --dial-timeout=2s --command-timeout=3s --endpoints=http://$1:2379 get "${@:2}" 2>/dev/null; }
islocal() { ip -o -4 addr show 2>/dev/null | grep -q " $1/"; }
usable() { case "$1" in ''|0.0.0.0|127.*) return 1 ;; esac; islocal $1 && return 1; return 0; }
ip=''; portal=''
usable "$nip" && ip=$nip
if [ -z "$ip" ]; then
	portal=`timeout ${HOSTALIVE_TCLITMO:-20} targetcli ls /iscsi/iqn.2016-03.com.$host:t1/tpg1/portals 2>/dev/null | sed -n 's/.*o- \([0-9][0-9.]*\):[0-9]*.*/\1/p' | tr '\n' ' '`
	for c in $portal; do usable $c && { ip=$c; break; }; done
fi
ready=''
if [ -z "$ip" ] && [ -n "$eip" ]; then
	ready=`et $eip ready/$host --print-value-only | head -1`
	usable "$ready" && ip=$ready
fi
[ -z "$ip" ] && { echo "hostalive $host: no address (given '${nip}', portal '${portal}', ready '${ready}'; local ones skipped)"; exit 2; }
r=0
while [ $r -lt $rounds ]; do
	r=$((r+1))
	ans=''
	ping -c 1 -W 1 $ip >/dev/null 2>&1 && ans=ping
	[ -z "$ans" ] && timeout 2 bash -c "</dev/tcp/$ip/2379" >/dev/null 2>&1 && ans=tcp2379
	if [ -n "$ans" ]; then
		name=`et $ip clusternode --print-value-only | head -1`
		if [ -n "$name" ] && [ "$name" != "$host" ]; then
			echo "hostalive $host: NOT alive, $ip answers ($ans) but its etcd names $name"; exit 1
		fi
		if [ -z "$name" ] && [ -n "$eip" ]; then
			# the etcd there is silent: is the address listed for another ready host (a node rebuilt under a new name)?
			list=`et $eip ready --prefix`
			rows=`printf '%s\n' "$list" | paste - - 2>/dev/null`
			other=`printf '%s\n' "$rows" | awk -v ip="$ip" -v h="ready/$host" '$2==ip && $1!=h && $1 ~ /^ready\// {sub(/^ready\//,"",$1); print $1; exit}'`
			mine=`printf '%s\n' "$rows" | awk -v ip="$ip" -v h="ready/$host" '$1==h && $2==ip {print "yes"; exit}'`
			if [ -n "$other" ] && [ -z "$mine" ]; then
				echo "hostalive $host: NOT alive, $ip answers ($ans) but is listed for $other (ready/$host missing or another ip)"; exit 1
			fi
			[ -n "$other" ] && { echo "hostalive $host: ALIVE, $ip answers ($ans) in round $r of $rounds; listed for $host and $other (ambiguous: kept alive, r10r3)"; exit 0; }
		fi
		echo "hostalive $host: ALIVE, $ip answers ($ans${name:+, etcd names $name}) in round $r of $rounds"; exit 0
	fi
	[ $r -lt $rounds ] && sleep ${HOSTALIVE_STEP:-2}
done
echo "hostalive $host: NOT alive, $ip did not answer ping or TCP 2379 in $rounds round(s)"
exit 1
