#!/bin/sh
cd /pace
echo $@ `date` > /root/hostlost
# container flavour: a dead node leaves its iSCSI target and its imported pools in the kernel all nodes share.
# The leader removes them and exports the pools, so the normal take over (poolnxt -> zpooltoimport.py) can run.
[ -f /TopStor/flavor.sh ] && . /TopStor/flavor.sh
# QSD5.352 r10i (QC proof 10h O3): never for this node itself.  heartbeat.py of the leader called this script for its OWN
# host once (its etcd was slow): the loop below deleted its own disks from sysfs and closthost.sh removed its own target
# and exported its pool, so the other node took the pool over.  Container flavour: refused and logged (the caller is fixed
# too, this is the second guard).
if is_container 2>/dev/null && [ -n "`echo $@ | awk '{print $5}'`" ] && [ "`echo $@ | awk '{print $5}'`" = "`echo $@ | awk '{print $3}'`" ]
then
	echo "`date '+%F %T'` hostlost.sh $@: refused, the lost host is this node itself (r10i)" >> /root/hostlostrefused.log
	exit 0
fi
# QSD5.352 r10r2 (QC proof r10r, candidate A): never for a host that answers.  A follower whose own etcd stalled took the
# LIVE leader for lost 32 times: the loop below deleted the leader's real SCSI devices from the kernel the containers share
# and closthost.sh removed its iSCSI target and backstores (3 pools DEGRADED).  Container flavour: hostalive.sh (6th
# argument = the host's node ip from heartbeat.py, else the portal of its target, else its ready/ record), one round;
# a host that answers is refused and logged, nothing is deleted.
hlhost=`echo $@ | awk '{print $5}'`; hlip=`echo $@ | awk '{print $6}'`; hlmyip=`echo $@ | awk '{print $4}'`
if is_container 2>/dev/null && [ -n "$hlhost" ]
then
	hlwhy=`${HOSTALIVE:-/pace/hostalive.sh} $hlhost "${hlip:--}" "${hlmyip:--}" 1`
	if [ $? -eq 0 ]
	then
		echo "`date '+%F %T'` hostlost.sh $@: refused, the host answers ($hlwhy) (r10r2)" >> ${HOSTLOST_REFUSED_LOG:-/root/hostlostrefused.log}
		exit 0
	fi
fi
if is_container 2>/dev/null && [ "`echo $@ | awk '{print $1}'`" = "`echo $@ | awk '{print $3}'`" ]
then
	setsid nohup /pace/closthost.sh $hlhost $hlip >/dev/null 2>&1 </dev/null &
fi
#export PATH=/bin:/usr/bin:/sbin:/usr/sbin:/root
leader=`echo $@ | awk '{print $1}'`
leaderip=`echo $@ | awk '{print $2}'`
myhost=`echo $@ | awk '{print $3}'`
myhostip=`echo $@ | awk '{print $4}'`
thehost=`echo $@ | awk '{print $5}'`
echo $leader | grep $myhost
if [ $? -eq 0 ];
then
	etcdip=$leaderip
else
	etcdip=$myhostip
fi
echo /pace/etcdget.py $etcdip ready --prefix \| grep $thehost
/pace/etcdget.py $etcdip ready --prefix | grep $thehost
if [ $? -ne 0 ];
then
 echo slslslslslslsl
 #exit
fi
echo hihihihi
declare -a disks=`lsscsi -i | grep $thehost | awk '{print $6" "$7}'`;
echo "${disks[@]}"
echo $@ > /root/losthostparam
echo "${disks[@]}" > /root/losthost
echo pdisks=` echo "${disks[@]}" | awk '{print $1}' | awk -F'/' '{print $NF}' `
echo pdisks="${pdisks[@]}" >> /root/losthost
echo  "${disks[@]}" | while read l;
do
   dis=`echo $l | awk '{print $1}'  | awk -F'/' '{print $3}'`
   echo 1 > /sys/block/$dis/device/delete 2>/dev/null
   echo echo 1 \> /sys/block/$dis/device/delete >> /root/hostlost
done
echo disks="${disks[@]}" >> /root/hostlosttmp
echo "${disks[@]}" | awk '{print $2}'  | while read l;
do
 echo checking disk $l >> /root/hostlosttmp
 ETCDCTL_API=3 /pace/changeop.py $leader $leaderip $etcdip $myhost $myhostip scsi-$l 
done
echo udpating database >> /root/hostlosttmp
/pace/etcddel.py $etcdip ready $thehost
