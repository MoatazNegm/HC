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
[ -f /TopStor/flavor.sh ] && . /TopStor/flavor.sh
# QSD5.352 r10r2 (QC proof r10r, candidate A), container flavour: (1) one take-over at a time (r10r: 3 leaderlost.sh were
# still piled up); (2) never take over from a leader that answers: in r10r a follower whose own etcd stalled ran this script
# 32 times against the live leader (two nodes on the cluster ip; the host-lost path that follows removed the leader's SCSI
# devices and target).  heartbeat.py probes the leader before it calls this script (HOSTALIVE_CHECKED=<lost host>: not
# probed twice); any other caller is probed here (hostalive.sh, one round; 9th argument = the lost leader's node ip).
# Refused: 'TAKEOVER REFUSED' / 'TAKEOVER BUSY' on stdout and in /root/heartproblem, exit 0, nothing changed.
llog() { echo "`date '+%F %T'` leaderlost.sh $*" >> ${LEADERLOST_LOG:-/root/heartproblem}; }
if is_container 2>/dev/null; then
 lk=${LEADERLOST_LOCK:-/TopStordata/leaderlost.lock}; [ -d "${lk%/*}" ] || lk=/tmp/leaderlost.lock
 exec 8>>$lk
 if ! flock -n 8; then
  llog "TAKEOVER BUSY: another leaderlost.sh runs, this one ($*) ends"
  echo "TAKEOVER BUSY: another leaderlost.sh runs"
  exit 0
 fi
 if [ "$HOSTALIVE_CHECKED" != "$losthost" ]; then
  why=`${HOSTALIVE:-/pace/hostalive.sh} $losthost "${9:--}" $myhostip 1`
  if [ $? -eq 0 ]; then
   llog "TAKEOVER REFUSED: the leader $losthost answers ($why)"
   echo "TAKEOVER REFUSED: the leader $losthost answers ($why)"
   exit 0
  fi
  llog "take-over from $losthost: $why"
 fi
fi
echo /TopStor/docker_primary.sh $leader $myhostip $leaderip $clusterip
/TopStor/docker_primary.sh $leader $myhostip $leaderip $clusterip 8>&-
# QSD5.352 r10r (QC proof 10q S-3, x2 575.4), container flavour: the new leader's schedule table (crontab, the lines
# that post the scheduled snapshots) was never rebuilt after a take-over, so a short table of this node (Hourly/Minutely
# lines lost) stayed and those snapshots stopped.  Once the etcd at the cluster address answers (3 min at most), the
# table is rebuilt from the Snapperiod records here (etctocron.py keeps the old table when the read fails).
# r10r2: at most ONE such background wait per node (a take-over while one waits starts no second one; the wait is capped).
if is_container 2>/dev/null; then
 ( exec 8>&-; wl=${ETCTOCRON_LOCK:-/TopStordata/etctocron-wait.lock}; [ -d "${wl%/*}" ] || wl=/tmp/etctocron-wait.lock
   exec 7>>$wl; flock -n 7 || exit 0
   n=0; until ETCDCTL_API=3 timeout 10 etcdctl --endpoints=http://$leaderip:2379 get leader >/dev/null 2>&1 || [ $n -ge ${ETCTOCRON_WAITS:-36} ]; do sleep 5; n=$((n+1)); done
   echo "`date '+%F %T'` leaderlost.sh: take-over by $myhost, schedule table rebuilt now (etcd wait $((n*5)) s)" >> ${ETCTOCRON_LOG:-/root/etctocron.log}
   cd /pace && /usr/bin/python3 ${ETCTOCRON_PY:-/pace/etctocron.py} $leaderip ) >/dev/null 2>&1 </dev/null &
fi
# The monitoring stack (prometheus + grafana are recreated, ~60 s) is started in the background, and only once the API
# answers (60 s at most): run in line it kept the heartbeat from finishing the take over (hostdown sync, clean up of the
# lost leader) for a minute, and its disk load made the API start take ~27 s instead of ~1 s.
( n=0; until curl -s -m 2 -o /dev/null http://$leaderip:5001/ || [ $n -ge 30 ]; do sleep 2; n=$((n+1)); done; /TopStor/promserver.sh $leaderip ) >/dev/null 2>&1 </dev/null 8>&- &
echo docker exec etcdclient /TopStor/logmsg.py Partst05 info system $myhost 
docker exec etcdclient /TopStor/logmsg.py Partst05 info system $myhost 
stamp=`date +%s%N`
docker exec etcdclient /TopStor/logmsg.py Partst02 warning system $losthost
/pace/etcddel.py $leaderip sync/leader/Add --prefix
/pace/etcdput.py $leaderip sync/leader/Add_${myhost}_$myip/request leader_$stamp
/pace/etcdput.py $leaderip sync/leader/Add_${myhost}_$myip/request/$myhost leader_$stamp
#/pace/etcddel.py $leaderip toimport/$myhost 
docker exec etcdclient /TopStor/etcdput.py etcd refreshdisown/$myhost yes
