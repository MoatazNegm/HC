#!/usr/bin/sh
# cpoolowner.sh -- CONTAINER flavour only.
# All containers of the dev cluster share ONE kernel, so a zpool is visible ("imported") in every node at once,
# while on physical servers a pool is imported on exactly one node.  The node that owns a pool is therefore
# written on the pool itself, as the zfs user property  topstor:owner=<host>:
#   cpoolowner.sh claim <host>          every imported pool that has no owner yet becomes <host>'s
#                                       (called by the node that has just created or imported a pool)
#   cpoolowner.sh set <host> <pool>     this pool is now <host>'s
#   cpoolowner.sh mine <host>           the pools of <host>, one per line (putzpool.py reports only these)
#   cpoolowner.sh of <pool>             the owner of <pool> ('-' when it has none)
cmd=$1
case $cmd in
claim)
	for p in `zpool list -H -o name 2>/dev/null`; do
		[ "`zfs get -H -o value topstor:owner $p 2>/dev/null`" = "-" ] && zfs set topstor:owner=$2 $p 2>/dev/null
	done ;;
set)
	zfs set topstor:owner=$2 $3 2>/dev/null ;;
mine)
	for p in `zpool list -H -o name 2>/dev/null`; do
		[ "`zfs get -H -o value topstor:owner $p 2>/dev/null`" = "$2" ] && echo $p
	done ;;
of)
	zfs get -H -o value topstor:owner $2 2>/dev/null ;;
esac
exit 0
