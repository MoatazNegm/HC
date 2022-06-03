#!/bin/sh
leadername=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
leaderip=`echo $@ | awk '{print $3}'`
myip=`echo $@ | awk '{print $4}'`
echo leader is dead..  >> /root/leaderlost
leaderfail=1
./etcdgetlocal.py $myip known --prefix | wc -l | grep 1
if [ $? -eq 0 ];
then
 /TopStor/logmsg.py Partst05 info system $myhost &
 primtostd=0;
fi
nextleadip=`ETCDCTL_API=3 ./etcdgetlocal.py $myip nextlead` 
echo nextlead is $nextleadip  >> /root/zfspingtmp
echo $nextleadip | grep $myip
if [ $? -eq 0 ];
then
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
  /TopStor/logqueue.py AddingMePrimary start system 
 fi
 echo hostlostlocal getting all my pools from $leadername >> /root/zfspingtmp
 ETCDCTL_API=3 /pace/hostlostlocal.sh $leadername $myip $leaderip
 systemctl stop etcd 2>/dev/null
 clusterip=`cat /pacedata/clusterip`
 echo starting primary etcd with namespace >> /root/zfspingtmp
 ./etccluster.py 'new' $myip 2>/dev/null
 chmod +r /etc/etcd/etcd.conf.yml
 systemctl daemon-reload 2>/dev/null
 systemctl start etcd 2>/dev/null
 ionice -c2 -n0 -p `pgrep etcd`
 while true;
 do
  echo starting etcd=$?
  systemctl status etcd
  if [ $? -eq 0 ];
  then
   break
  else
   sleep 1
  fi
 done
 echo adding me as a leader >> /root/zfspingtmp
 rm -rf /etc/chrony.conf
 cp /TopStor/chrony.conf /etc/
 sed -i '/MASTERSERVER/,+1 d' /etc/chrony.conf
 ./runningetcdnodes.py $myip 2>/dev/null
 ./etcddel.py leader --prefix 2>/dev/null &
 ./etcdput.py leader/$myhost $myip 2>/dev/null &
 ./etcddel.py ready --prefix 2>/dev/null &
 ./etcdput.py ready/$myhost $myip 2>/dev/null &
else
 ETCDCTL_API=3 /pace/hostlostlocal.sh $leadername $myip $leaderip
 systemctl stop etcd 2>/dev/null 
 echo starting waiting for new leader run >> /root/zfspingtmp
 waiting=1
 result='nothing'
 while [ $waiting -eq 1 ]
 do
  echo still looping for new leader run >> /root/zfspingtmp
  echo $result | grep nothing 
  if [ $? -eq 0 ];
  then
   sleep 1 
   result=`ETCDCTL_API=3 ./nodesearch.py $myip 2>/dev/null`
  else
   echo $perfmon | grep 1
   if [ $? -eq 0 ]; then
    /TopStor/logqueue.py AddingtoOtherleader start system 
   fi
   echo found the new leader run $result >> /root/zfspingtmp
   waiting=0
   /pace/syncthtistoleader.py $myip pools/ $myhost
   /pace/syncthtistoleader.py $myip volumes/ $myhost
   /pace/etcdput.py ready/$myhost $myip
   /pace/etcdput.py tosync/$myhost $myip
   /TopStor/broadcast.py SyncHosts /TopStor/pump.sh addhost.py 
   leaderall=` ./etcdget.py leader --prefix `
   leader=`echo $leaderall | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
   leaderip=` ./etcdget.py leader/$leader `
   rm -rf /etc/chrony.conf
   cp /TopStor/chrony.conf /etc/
   sed -i "s/MASTERSERVER/$leaderip/g" /etc/chrony.conf
   systemctl restart chronyd
   echo $perfmon | grep 1
   if [ $? -eq 0 ]; then
    /TopStor/logqueue.py AddingtoOtherleader start system 
   fi
  fi
 done 
 leadername=`./etcdget.py leader --prefix | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
 continue
fi
 
