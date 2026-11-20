#!/bin/sh
echo $@ > /root/leaderlost
cd /pace
leader=`echo $@ | awk '{print $1}'`
leaderip=`echo $@ | awk '{print $2}'`
myhost=`echo $@ | awk '{print $3}'`
myhostip=`echo $@ | awk '{print $4}'`
myip=$myhostip
nextlead=`echo $@ | awk '{print $5}'`
nextleadip=`echo $@ | awk '{print $6}'`
clusterip=`echo $@ | awk '{print $7}'`
losthost=`echo $@ | awk '{print $8}'`
enpdev='enp0s8'


#rm -rf /etc/chrony.conf
#cp /TopStor/chrony.conf /etc/
#sed -i "s/MASTERSERVER/$nextleadip/g" /etc/chrony.conf
#systemctl restart chronyd
echo $myhost | grep $nextlead 
if [ $? -ne 0 ];
then
  echo leader is dead but another process was in the way to fix.  >> /root/zfspingtmp2
  echo leader is dead but another process was in the way to fix.
  exit
fi
echo /TopStor/docker_primary.sh $leader $myhostip $leaderip $clusterip
/TopStor/docker_primary.sh $leader $myhostip $leaderip $clusterip
# QSD5.352 r10r (QC proof 10q S-3, x2 575.4), container flavour: the new leader's schedule table (crontab, the lines
# that post the scheduled snapshots) was never rebuilt after a take-over, so a short table of this node (Hourly/Minutely
# lines lost) stayed and those snapshots stopped.  Once the etcd at the cluster address answers (3 min at most), the
# table is rebuilt from the Snapperiod records here (etctocron.py keeps the old table when the read fails).
[ -f /TopStor/flavor.sh ] && . /TopStor/flavor.sh
if is_container 2>/dev/null; then
 ( n=0; until ETCDCTL_API=3 timeout 10 etcdctl --endpoints=http://$leaderip:2379 get leader >/dev/null 2>&1 || [ $n -ge ${ETCTOCRON_WAITS:-36} ]; do sleep 5; n=$((n+1)); done
   echo "`date '+%F %T'` leaderlost.sh: take-over by $myhost, schedule table rebuilt now (etcd wait $((n*5)) s)" >> ${ETCTOCRON_LOG:-/root/etctocron.log}
   cd /pace && /usr/bin/python3 ${ETCTOCRON_PY:-/pace/etctocron.py} $leaderip ) >/dev/null 2>&1 </dev/null &
fi
# The monitoring stack (prometheus + grafana are recreated, ~60 s) is started in the background, and only once the API
# answers (60 s at most): run in line it kept the heartbeat from finishing the take over (hostdown sync, clean up of the
# lost leader) for a minute, and its disk load made the API start take ~27 s instead of ~1 s.
( n=0; until curl -s -m 2 -o /dev/null http://$leaderip:5001/ || [ $n -ge 30 ]; do sleep 2; n=$((n+1)); done; /TopStor/promserver.sh $leaderip ) >/dev/null 2>&1 </dev/null &
echo docker exec etcdclient /TopStor/logmsg.py Partst05 info system $myhost 
docker exec etcdclient /TopStor/logmsg.py Partst05 info system $myhost 
stamp=`date +%s%N`
docker exec etcdclient /TopStor/logmsg.py Partst02 warning system $losthost
/pace/etcddel.py $leaderip sync/leader/Add --prefix
/pace/etcdput.py $leaderip sync/leader/Add_${myhost}_$myip/request leader_$stamp
/pace/etcdput.py $leaderip sync/leader/Add_${myhost}_$myip/request/$myhost leader_$stamp
#/pace/etcddel.py $leaderip toimport/$myhost 
docker exec etcdclient /TopStor/etcdput.py etcd refreshdisown/$myhost yes
