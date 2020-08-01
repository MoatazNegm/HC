#!/usr/bin/sh
cd /pace
export ETCDCTL_API=3
ETCDCTL_API=3
echo $$ > /var/run/zfsping.pid
targetcli clearconfig True
targetcli saveconfig
targetcli restoreconfig /pacedata/targetconfig
targetcli saveconfig
failddisks=''
oldlsscsi='00'
isknown=0
leaderfail=0
ActivePartners=1
partnersync=0
readycount=1
isprimary=0
primtostd=4
toimport=-1
clocker=0
oldclocker=0
clockdiff=0
date=`date`
enpdev='enp0s8'
echo $date >> /root/zfspingstart
systemctl restart target
cd /pace
rm -rf /pacedata/addiscsitargets 2>/dev/null
rm -rf /pacedata/startzfsping 2>/dev/null
while [ ! -f /pacedata/startzfsping ];
do
 sleep 1;
 echo cannot run now > /root/zfspingtmp
done
echo startzfs run >> /root/zfspingtmp
/pace/startzfs.sh
leadername=` ./etcdget.py leader --prefix | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
leaderip=` ./etcdget.py leader/$leadername `
date=`date `
myhost=`hostname -s`
myip=`/sbin/pcs resource show CC | grep Attributes | awk -F'ip=' '{print $2}' | awk '{print $1}'`
echo starting in $date >> /root/zfspingtmp
while true;
do
 pgrep fixpool 
 if [ $? -ne 0 ];
 then
  /TopStor/fixpool.py  &
 fi
 perfmon=`cat /pacedata/perfmon`
 needlocal=0
 runningcluster=0
 touch /var/www/html/des20/Data/TopStorqueue.log
 chown apache /var/www/html/des20/Data/TopStorqueue.log
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
 /TopStor/queuethis.sh AmIprimary start system &
 fi
  
 echo check if I primary etcd >> /root/zfspingtmp
 netstat -ant | grep 2379 | grep LISTEN &>/dev/null
 if [ $? -eq 0 ]; 
 then
  echo I am primary etcd,isprimary:$isprimary >> /root/zfspingtmp
  if [[ $isprimary -le 10 ]];
  then
   isprimary=$((isprimary+1))
  fi
  if [[ $primtostd -le 10 ]];
  then
   primtostd=$((primtostd+1))
  fi
  if [ $primtostd -eq 3 ];
  then
   /TopStor/logmsg.py Partsu05 info system $myhost
   primtostd=$((primtostd+1))
  fi
  if [ $isprimary -eq 3 ];
  then
   echo for $isprimary sending info Partsu03 booted with ip >> /root/zfspingtmp
   /pace/etcdput.py ready/$myhost $myip
   /pace/etcdput.py ActivePartners/$myhost $myip
   partnersync=0
   /TopStor/broadcast.py SyncHosts /TopStor/pump.sh addhost.py 
   touch /pacedata/addiscsitargets 
   pgrep putzpool 
   if [ $? -ne 0 ];
   then
    /pace/putzpool.py 1 $isprimary $primtostd  &
   fi
   ./etcddel.py toimport/$myhost
   toimport=2
  fi
  runningcluster=1
  echo checking leader record \(it should be me\)  >> /root/zfspingtmp
  leaderall=` ./etcdget.py leader --prefix 2>/dev/null`
  if [[ -z $leaderall ]]; 
  then
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
   /TopStor/queuethis.sh FixIamleader start system &
 fi
   echo no leader although I am primary node >> /root/zfspingtmp
   ./runningetcdnodes.py $myip 2>/dev/null
   ./etcddel.py leader --prefix 2>/dev/null &
   ./etcdput.py leader/$myhost $myip 2>/dev/null &
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
   /TopStor/queuethis.sh FixIamleader stop system &
 fi
  fi
  echo adding known from list of possbiles >> /root/zfspingtmp
   pgrep  addknown 
   if [ $? -ne 0 ];
   then
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
    /TopStor/queuethis.sh addingknown start system &
 fi
    ./addknown.py 2>/dev/null & 
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
    /TopStor/queuethis.sh addingknown stop system &
 fi 
   fi
 echo checking if there are partners to sync >> /root/zfspingtmp
 tosync=`ETCDCTL_API=3 /pace/etcdget.py tosync --prefix | wc -l `
 if [ $tosync -gt 0 ];
 then
  ETCDCTL_API=3 /pace/etcddel.py tosync --prefix
  echo syncthing with the ready to sync partners >> /root/zfspingtmp
  ./syncthis.py ready --prefix 
  ./syncthis.py pools/ --prefix 
  ./syncthis.py volumes/ --prefix 
  ./syncthis.py ActivePartners --prefix 
  ./syncthis.py allowedPartners --prefix 
  ./syncthis.py frstnode --prefix 
 else
  readycount=`ETCDCTL_API=3 /pace/etcdget.py ready --prefix | wc -l` 
  lostcount=`ETCDCTL_API=3 /pace/etcdget.py lost --prefix | wc -l` 
  totalin=$(readycount+lostcount)
  ActivePartners=`ETCDCTL_API=3 /pace/etcdget.py ActivePartners --prefix | wc -l` 
  if [ $totalin -eq $ActivePartners ];
  then  
   echo All running partners are ready and in sync >> /root/zfspingtmp
  else
   echo some partners are not in sync >> /root/zfspingtmp
   ./etcdput.py tosync yes
  fi
 fi
 else
  echo I am not a primary etcd.. heartbeating leader >> /root/zfspingtmp
  leaderall=` ./etcdget.py leader --prefix 2>&1`
  echo $leaderall | grep Error  &>/dev/null
  if [ $? -eq 0 ];
  then
   echo leader is dead..  >> /root/zfspingtmp
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
    /TopStor/queuethis.sh AddingMePrimary start system &
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
   #./etcdput.py clusterip $clusterip 2>/dev/null
   #pcs resource create clusterip ocf:heartbeat:IPaddr nic="$enpdev" ip=$clusterip cidr_netmask=24 2>/dev/null
    echo adding me as a leader >> /root/zfspingtmp
    rm -rf /etc/chrony.conf
    cp /TopStor/chrony.conf /etc/
    sed -i '/MASTERSERVER/,+1 d' /etc/chrony.conf
    ./runningetcdnodes.py $myip 2>/dev/null
    ./etcddel.py leader 2>/dev/null &
    ./etcdput.py leader/$myhost $myip 2>/dev/null &
    ./etcddel.py ready --prefix 2>/dev/null &
    ./etcdput.py ready/$myhost $myip 2>/dev/null &
    ./etcdput.py tosync/$myhost $myip 2>/dev/null &
#    ETCDCTL_API=3 /pace/hostlost.sh $leadername &
    /TopStor/logmsg.py Partst02 warning system $leaderall &
    
    echo creating namespaces >>/root/zfspingtmp
    ./setnamespace.py $enpdev &
    ./setdataip.py &
    echo created namespaces >>/root/zfspingtmp
   # systemctl restart smb 2>/dev/null &
    echo importing all pools >> /root/zfspingtmp
    ./etcddel.py toimport/$myhost &
    toimport=1
    #/sbin/zpool import -am &>/dev/null
    echo running putzpool and nfs >> /root/zfspingtmp
    pgrep putzpool 
    if [ $? -ne 0 ];
    then
     /pace/putzpool.py 2 $isprimary $primtostd  &
     /TopStor/HostgetIPs
    fi
#    systemctl status nfs 
#    if [ $? -ne 0 ];
#    then
#     systemctl start nfs 2>/dev/null
#    fi
    chgrp apache /var/www/html/des20/Data/* 2>/dev/null
    chmod g+r /var/www/html/des20/Data/* 2>/dev/null
    runningcluster=1
    leadername=$myhost
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
    /TopStor/queuethis.sh AddinMePrimary stop system &
 fi
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
      /TopStor/queuethis.sh AddingtoOtherleader start system &
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
      /TopStor/queuethis.sh AddingtoOtherleader start system &
 fi
     fi
    done 
    leadername=`./etcdget.py leader --prefix | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
    continue
   fi
  else 
   echo I am not primary.. checking if I am local etcd>> /root/zfspingtmp
   netstat -ant | grep 2378 | grep $myip | grep LISTEN &>/dev/null
   if [ $? -ne 0 ];
   then
    echo I need to be local etcd .. no etcd is running>> /root/zfspingtmp
    needlocal=1
   else
    echo local etcd is already running>> /root/zfspingtmp
    needlocal=2
   fi
   echo checking if I am known host >> /root/zfspingtmp
   known=` ./etcdget.py known --prefix 2>/dev/null`
   myconfig=` ./etcdgetlocal.py $myip configured 2>/dev/null`

   echo $known | grep $myhost  &>/dev/null
   if [ $? -ne 0 ];
   then
    echo $myconfig | grep yes  &>/dev/null
    if [ $? -ne 0 ];
    then
     echo I am not a known and I am not configured. So, adding me as possible >> /root/zfspingtmp
     ./etcdput.py possible$myhost $myip 2>/dev/null &
    else
     echo I am not a known but I am configured so need to activate >> /root/zfspingtmp
     ./etcdput.py toactivate$myhost $myip 2>/dev/null &
    fi 
   else
   echo $perfmon | grep 1
   if [ $? -eq 0 ]; then
     /TopStor/queuethis.sh iamkknown start system &
   fi
   echo I am known so running all needed etcd task:boradcast,isknown:$isknown >> /root/zfspingtmp
    if [[ $isknown -eq 0 ]];
    then
     echo running sendhost.py $leaderip 'user' 'recvreq' $myhost >>/root/tmp2
     leaderall=` ./etcdget.py leader --prefix `
     leader=`echo $leaderall | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
     leaderip=`echo $leaderall | awk -F"')" '{print $1}' | awk -F", '" '{print $2}'`
     #/pace/sendhost.py $leaderip 'user' 'recvreq' $myhost &
     /pace/etcdsync.py $myip pools pools 2>/dev/null
     /pace/etcdsync.py $myip poolsnxt poolsnxt 2>/dev/null
     /pace/etcdsync.py $myip nextlead nextlead 2>/dev/null
     #/pace/sendhost.py $leaderip 'cifs' 'recvreq' $myhost &
     /pace/sendhost.py $leaderip 'logall' 'recvreq' $myhost &
     isknown=$((isknown+1))
    fi
    if [[ $isknown -le 10 ]];
    then
     isknown=$((isknown+1))
    fi
    if [[ $isknown -eq 3 ]];
    then
     /pace/etcdput.py ready/$myhost $myip &
     /pace/etcdput.py ActivePartners/$myhost $myip &
     /TopStor/broadcast.py SyncHosts /TopStor/pump.sh addhost.py
     #targetcli clearconfig True
     #targetcli saveconfig
     #targetcli restoreconfig /pacedata/targetconfig
     touch /pacedata/addiscsitargets 
   ./etcddel.py toimport/$myhost &
     toimport=1
    fi
    echo finish running tasks task:boradcast, log..etc >> /root/zfspingtmp
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
    /TopStor/queuethis.sh iamkknown stop system &
 fi
   fi
  fi 
 fi
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
 /TopStor/queuethis.sh AmIprimary stop system &
 fi
 pgrep putzpool 
 if [ $? -ne 0 ];
 then
  /pace/putzpool.py 3 $isprimary $primtostd  &
 fi
 echo checking if I need to run local etcd >> /root/zfspingtmp
 if [[ $needlocal -eq 1 ]];
 then
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
  /TopStor/queuethis.sh IamLocal start system &
 fi
  echo start the local etcd >> /root/zfspingtmp
  ./etccluster.py 'local' $myip 2>/dev/null
  chmod +r /etc/etcd/etcd.conf.yml
  systemctl daemon-reload
  systemctl stop etcd 2>/dev/null
  systemctl start etcd 2>/dev/null
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
  leaderall=` ./etcdget.py leader --prefix `
  leader=`echo $leaderall | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
  leaderip=`echo $leaderall | awk -F"')" '{print $1}' | awk -F", '" '{print $2}'`
  ./etcdsync.py $myip primary primary 2>/dev/null &
  ./etcddellocal.py $myip known --prefix 2>/dev/null &
  ./etcddellocal.py $myip localrun --prefix 2>/dev/null &
  ./etcddellocal.py $myip run --prefix 2>/dev/null &
  ./etcdsync.py $myip known known 2>/dev/null &
  ./etcdsync.py $myip localrun localrun 2>/dev/null &
  ./etcdsync.py $myip leader known 2>/dev/null &
#   ./etcddellocal.py $myip known/$myhost --prefix 2>/dev/null
  echo done and exit >> /root/zfspingtmp
  continue 
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
  /TopStor/queuethis.sh IamLocal stop system &
 fi
 fi
 if [[ $needlocal -eq  2 ]];
 then
  echo I am already local etcd running iscsirefresh on $myip $myhost  >> /root/zfspingtmp
  pgrep iscsiwatchdog
  if [ $? -ne 0 ];
  then
   /pace/iscsiwatchdog.sh $myip $myhost $leader 2>/dev/null &
  fi
 fi
 echo checking if still in the start initcron is still running  >> /root/zfspingtmp
 if [ -f /pacedata/forzfsping ];
 then
  echo Yes. so I have to exit >> /root/zfspingtmp
  continue
 fi
 cd /pace
 echo No then Checking Node Evacuation >> /root/zfspingtmp
 pgrep Evacuatelocal
 if [ $? -ne 0 ];
 then
  /TopStor/Evacuatelocal.py
  cd /pace
 fi
 echo Checking  I am primary >> /root/zfspingtmp
 if [[ $runningcluster -eq 1 ]];
 then
  echo Yes I am primary so will check for known hosts >> /root/zfspingtmp
   pgrep  remknown 
   if [ $? -ne 0 ];
   then
    ./remknown.py $myhost 2>/dev/null & 
   fi
   pgrep  addknown 
   if [ $? -ne 0 ];
   then
    ./addknown.py $myhost 2>/dev/null & 
   fi
   pgrep addactive 
   if [ $? -ne 0 ];
   then
    ./addactive.py $myhost 2>/dev/null & 
   fi
   pgrep  selectimport 
   if [ $? -ne 0 ];
   then
    /TopStor/selectimport.py $myhost &
   fi
 fi 
 echo toimport = $toimport >> /root/zfspingtmp
 
 if [ $toimport -gt 0 ];
 then
  ETCDCTL_API=3 /pace/etcdget.py toimport/$myhost 
  mytoimport=`ETCDCTL_API=3 /pace/etcdget.py toimport/$myhost`
  if [ $mytoimport == '-1' ]; then 
   echo Yes  I have no record in toimport/$myhost even no nothing=$mytoimport >> /root/zfspingtmp
  fi
  echo $mytoimport | grep nothing
  if [ $? -eq 0 ];
  then
   echo it is nothing , toimport=$toimport >> /root/zfspingtmp
   if [ $toimport -eq 1 ];
   then
    if [ $leaderfail -eq 0 ];
    then
     /TopStor/logmsg.py Partsu04 info system $myhost $myip &
     ./etcddel.py cann --prefix 2>/dev/null &
    else
     leaderfail=0
    fi
   fi
   if [ $toimport -eq 2 ];
   then
    if [ $leaderfail -eq 0 ];
    then
     /TopStor/logmsg.py Partsu03 info system $myhost $myip &
     ./etcddel.py cann --prefix 2>/dev/null &
    else
     leaderfail=0
    fi
     
   fi
   if [ $toimport -eq 3 ];
   then
    /TopStor/logmsg.py Partsu06 info system &
   fi
   toimport=0
   oldclocker=$clocker
  else
   echo checking zpool to import>> /root/zfspingtmp
   lsscsi=`lsscsi | wc -c`'lsscsi'
   pgrep zpooltoimport
   if [ $? -ne 0 ];
   then
    /TopStor/zpooltoimport.py all &
    oldlsscsi=$lsscsi
   fi
   pgrep  VolumeCheck 
   if [ $? -ne 0 ];
   then
    /TopStor/VolumeCheck
   fi
  fi
 fi
 if [ $toimport -eq 0 ];
 then
  clocker=`date +%s`
  clockdiff=$((clocker-oldclocker))
 fi
 echo Clockdiff = $clockdiff >> /root/zfspingtmp
 if [ $clockdiff -ge 500 ];
 then
  ./etcddel.py toimport/$myhost &
  /TopStor/logmsg.py Partst06 info system  &
  toimport=3
  oldclocker=$clocker
  clockdiff=0
 fi
 pgrep iscsiwatchdog
 if [ $? -ne 0 ];
 then
  /pace/iscsiwatchdog.sh 2>/dev/null  &
 fi
  echo Collecting a change in system occured >> /root/zfspingtmp
 #/pace/changeop.py hosts/$myhost/current d
   pgrep  changeop 
   if [ $? -ne 0 ];
   then
    ETCDCTL_API=3 /pace/changeop.py $myhost &
   fi
   pgrep  selectspare 
   if [ $? -ne 0 ];
   then
    ETCDCTL_API=3 /pace/selectspare.py $myhost &
   fi
done
