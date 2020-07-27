#!/usr/bin/sh
cd /pace
export ETCDCTL_API=3
ETCDCTL_API=3
echo $$ > /var/run/zfsping.pid
targetcli clearconfig True >/dev/null
targetcli saveconfig >/dev/null
targetcli restoreconfig /pacedata/targetconfig >/dev/null
targetcli saveconfig >/dev/null
touch /pacedata/perfmon
failddisks=''
oldlsscsi='00'
lsscsicount=0
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
/pace/collective.py &
systemctl restart target >/dev/null
cd /pace
rm -rf /pacedata/addiscsitargets 2>/dev/null
#rm -rf /pacedata/startzfsping 2>/dev/null
#while [ ! -f /pacedata/startzfsping ];
#do
#  sleep 1;
#  echo cannot run now > /root/zfspingtmp
#done
#echo startzfs run >> /root/zfspingtmp
#/pace/startzfs.sh
leadername=` ./etcdget.py leader --prefix | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
leaderip=` ./etcdget.py leader/$leadername `
date=`date `
myhost=`hostname -s`
myip=`/sbin/pcs resource show CC | grep Attributes | awk -F'ip=' '{print $2}' | awk '{print $1}'`
echo starting in $date >> /root/zfspingtmp
lsscsiflag='init'
basetime=`date +%s`
origtime=`date +%s`
newtime=`date +%s`
echo before loop $((newtime-basetime)) ,total=$((newtime-origtime))> /root/zfspingtiming
basetime=$newtime
ostamp=0
while true;
do
 lsscsi=`lsscsi | wc -c`'lsscsi' >/dev/null
 echo $lsscsi | grep $oldsscsi
 if [ $? -eq 0 ];
 then
  lsscsiflag='zpooltoimport'
 fi 
newtime=`date +%s`
echo starting new loop $((newtime-basetime)) ,total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
origtime=$newtime
  echo $ostamp fixpool  $myhost > /pacedata/fixpool &
  ostamp=$((ostamp+1))
  perfmon=`cat /pacedata/perfmon `
  needlocal=0
  runningcluster=0
  touch /var/www/html/des20/Data/TopStorqueue.log
  chown apache /var/www/html/des20/Data/TopStorqueue.log
  echo $perfmon | grep 1 >/dev/null
  if [ $? -eq 0 ];
  then
   stamp=`date +%s`
   echo $ostamp logqueue AmIprimary start system $stamp > /pacedata/isprimary & 
   ostamp=$((ostamp+1))
  fi
  echo check if I primary etcd >> /root/zfspingtmp
newtime=`date +%s`
echo checkifprimary  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo check if I primary etcd 
  netstat -ant | grep 2379 | grep LISTEN >/dev/null
  if [ $? -eq 0 ]; 
  then
    echo I am primary etcd,isprimary:$isprimary >> /root/zfspingtmp
    echo I am primary etcd,isprimary:$isprimary
newtime=`date +%s`
echo Iamprimary  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
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
     echo $ostamp logmsg Partsu05 info system $myhost > /pacedata/isprimary & 
     ostamp=$((ostamp+1))
     primtostd=$((primtostd+1))
    fi
    if [ $isprimary -eq 3 ];
    then
      echo for $isprimary sending info Partsu03 booted with ip >> /root/zfspingtmp
newtime=`date +%s`
echo sendinginfo  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo for $isprimary sending info Partsu03 booted with ip
      echo $ostamp  etcdput ready/$myhost $myip > /pacedata/isprimary & 
      ostamp=$((ostamp+1))
      echo $ostamp  etcdput ActivePartners/$myhost $myip > /pacedata/isprimary & 
      ostamp=$((ostamp+1))
      partnersync=0
      echo $ostamp  broadcastthis SyncHosts /TopStor/pump.sh addhost.py > /pacedata/isprimary & 
      ostamp=$((ostamp+1))
      touch /pacedata/addiscsitargets 
      echo $ostamp  etcddel toimport/$myhost > /pacedata/isprimary & 
      ostamp=$((ostamp+1))
      toimport=2
      echo $lsscsiflag | grep putzpool
      if [ $? -eq 0 ];
      then
       pgrep putzpool 
       if [ $? -ne 0 ];
       then
         stamp=`date +%s`
         echo $ostamp  putzpool $stamp no1 $isprimary $primtostd > /pacedata/putzpool & 
         ostamp=$((ostamp+1))
         /pace/putzpool.py 1 $isprimary $primtostd  >/dev/null 
         /TopStor/HostgetIPs >/dev/null
         lsscsiflag=`echo $lsscsiflag | sed 's/putzpool/init/g'`
       fi
      fi
    fi
    runningcluster=1
    echo checking leader record \(it should be me\)  >> /root/zfspingtmp
newtime=`date +%s`
echo checkingleader  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo checking leader record \(it should be me\) 
    leaderall=` ./etcdget.py leader --prefix `
    if [[ -z $leaderall ]]; 
    then
      echo $perfmon | grep 1 >/dev/null
      if [ $? -eq 0 ];
      then
        /TopStor/queuethis.sh FixIamleader start system 
      fi
      echo no leader although I am primary node >> /root/zfspingtmp
newtime=`date +%s`
echo noleaderalthough  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo no leader although I am primary node 
      ./runningetcdnodes.py $myip >/dev/null
      ./etcddel.py leader --prefix >/dev/null 
      ./etcdput.py leader/$myhost $myip >/dev/null 
      echo $perfmon | grep 1 >/dev/null
      if [ $? -eq 0 ];
      then
        /TopStor/queuethis.sh FixIamleader stop system >/dev/null 
      fi
    fi
    echo adding known from list of possbiles >> /root/zfspingtmp
newtime=`date +%s`
echo addingknown  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo adding known from list of possbiles 
    pgrep  addknown 
    if [ $? -ne 0 ];
    then
      echo $perfmon | grep 1 >/dev/null
      if [ $? -eq 0 ];
      then
        /TopStor/queuethis.sh addingknown start system 
      fi
      ./addknown.py >/dev/null  
      echo $perfmon | grep 1
      if [ $? -eq 0 ];
      then
        /TopStor/queuethis.sh addingknown stop system 
      fi 
    fi
    echo checking if there are partners to sync >> /root/zfspingtmp
newtime=`date +%s`
echo checingifpartnertosync  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo checking if there are partners to sync
    tosync=`ETCDCTL_API=3 /pace/etcdget.py tosync --prefix | wc -l `
    if [ $tosync -gt 0 ];
    then
      ETCDCTL_API=3 /pace/etcddel.py tosync --prefix >/dev/null
      echo syncthing with the ready to sync partners >> /root/zfspingtmp
newtime=`date +%s`
echo synthingwithreadypartners  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo syncthing with the ready to sync partners 
      ./syncthis.py ready --prefix  >/dev/null
      ./syncthis.py pools/ --prefix >/dev/null
      ./syncthis.py volumes/ --prefix >/dev/null 
      ./syncthis.py ActivePartners --prefix /dev/null 
      ./syncthis.py allowedPartners --prefix /dev/null 
      ./syncthis.py frstnode --prefix /dev/null 
    else
      readycount=`ETCDCTL_API=3 /pace/etcdget.py ready --prefix | wc -l` 
      lostcount=`ETCDCTL_API=3 /pace/etcdget.py lost --prefix | wc -l` 
      totalin=$((readycount+lostcount))
      ActivePartners=`ETCDCTL_API=3 /pace/etcdget.py ActivePartners --prefix | wc -l` 
      if [ $totalin -eq $ActivePartners ];
      then  
        echo All running partners are ready and in sync >> /root/zfspingtmp
newtime=`date +%s`
echo allrunningpartners  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo All running partners are ready and in sync 
      else
        echo some partners are not in sync >> /root/zfspingtmp
newtime=`date +%s`
echo someprtnersnotinsync $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo some partners are not in sync
        ./etcdput.py tosync yes
      fi
    fi
  else
    echo I am not a primary etcd.. heartbeating leader >> /root/zfspingtmp
newtime=`date +%s`
echo  heartbeatingleader $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo I am not a primary etcd.. heartbeating leader 
    leaderall=` ./etcdget.py leader --prefix 2>/dev/null`
    echo $leaderall | grep Error  >/dev/null
    if [ $? -eq 0 ];
    then
      echo leader is dead..  >> /root/zfspingtmp
newtime=`date +%s`
echo  leaderisdead $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo leader is dead.. 
      leaderfail=1
      ./etcdgetlocal.py $myip known --prefix | wc -l | grep 1
      if [ $? -eq 0 ];
      then
        /TopStor/logmsg.py Partst05 info system $myhost >/dev/null 
        primtostd=0;
      fi
      nextleadip=`ETCDCTL_API=3 ./etcdgetlocal.py $myip nextlead` 
      echo nextlead is $nextleadip  >> /root/zfspingtmp
newtime=`date +%s`
echo  nextleadis $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo leader is dead.. 
      echo nextlead is $nextleadip 
      echo $nextleadip | grep $myip >/dev/null
      if [ $? -eq 0 ];
      then
        echo $perfmon | grep 1 >/dev/null
        if [ $? -eq 0 ]; then
          /TopStor/queuethis.sh AddingMePrimary start system 
        fi
        echo hostlostlocal getting all my pools from $leadername >> /root/zfspingtmp
newtime=`date +%s`
echo  hostlostlocal $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo hostlostlocal getting all my pools from $leadername
        ETCDCTL_API=3 /pace/hostlostlocal.sh $leadername $myip $leaderip
        systemctl stop etcd 2>/dev/null
        echo starting primary etcd with namespace >> /root/zfspingtmp
newtime=`date +%s`
echo startingprimary $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo starting primary etcd with namespace 
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
        echo adding me as a leader >> /root/zfspingtmp
newtime=`date +%s`
echo addingmeasleader $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo adding me as a leader
        rm -rf /etc/chrony.conf
        cp /TopStor/chrony.conf /etc/
        sed -i '/MASTERSERVER/,+1 d' /etc/chrony.conf
        ./runningetcdnodes.py $myip >/dev/null
        ./etcddel.py leader >/dev/null 
        ./etcdput.py leader/$myhost $myip >/dev/null 
        ./etcddel.py ready --prefix >/dev/null 
        ./etcdput.py ready/$myhost $myip >/dev/null 
        ./etcdput.py tosync/$myhost $myip >/dev/null 
        /TopStor/logmsg.py Partst02 warning system $leaderall 
        echo creating namespaces >>/root/zfspingtmp
newtime=`date +%s`
echo creatingnamespaces $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo creating namespaces 
        ./setnamespace.py $enpdev >/dev/null 
        ./setdataip.py >/dev/null 
        echo created namespaces >>/root/zfspingtmp
newtime=`date +%s`
echo creatednamespaces $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo created namespaces 
        echo importing all pools >> /root/zfspingtmp
        echo importing all pools
        ./etcddel.py toimport/$myhost >/dev/null 
        toimport=1
        echo running putzpool and nfs >> /root/zfspingtmp
newtime=`date +%s`
echo runningputzpool $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo running putzpool and nfs
        echo $lsscsiflag | grep putzpool
        if [ $? -eq 0 ];
        then
         pgrep putzpool 
         if [ $? -ne 0 ];
         then
          /pace/putzpool.py 2 $isprimary $primtostd  >/dev/null 
          /TopStor/HostgetIPs >/dev/null
          lsscsiflag=`echo $lsscsiflag | sed 's/putzpool/init/g'`
         fi
        fi
        chgrp apache /var/www/html/des20/Data/* >/dev/null
        chmod g+r /var/www/html/des20/Data/* >/dev/null
        runningcluster=1
        leadername=$myhost
        echo $perfmon | grep 1 >/dev/null
        if [ $? -eq 0 ];
        then
          /TopStor/queuethis.sh AddinMePrimary stop system 
        fi
      else
        ETCDCTL_API=3 /pace/hostlostlocal.sh $leadername $myip $leaderip >/dev/null
        systemctl stop etcd 2>/dev/null 
        echo starting waiting for new leader run >> /root/zfspingtmp
newtime=`date +%s`
echo startwaitingfornewleader $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo starting waiting for new leader run 
        waiting=1
        result='nothing'
        while [ $waiting -eq 1 ]
        do
          echo still looping for new leader run >> /root/zfspingtmp
newtime=`date +%s`
echo loopingfornew leader $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
          echo still looping for new leader run 
          echo $result | grep nothing >/dev/null 
          if [ $? -eq 0 ];
          then
            sleep 1 
            result=`ETCDCTL_API=3 ./nodesearch.py $myip 2>/dev/null`
          else
            echo $perfmon | grep 1 >/dev/null
            if [ $? -eq 0 ];
            then
              /TopStor/queuethis.sh AddingtoOtherleader start system 
            fi
            echo found the new leader run $result >> /root/zfspingtmp
newtime=`date +%s`
echo foundthenewleader $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
            echo found the new leader run $result
            waiting=0
            /pace/syncthtistoleader.py $myip pools/ $myhost >/dev/null
            /pace/syncthtistoleader.py $myip volumes/ $myhost >/dev/null
            /pace/etcdput.py ready/$myhost $myip /dev/null
            /pace/etcdput.py tosync/$myhost $myip /dev/null
            /TopStor/broadcast.py SyncHosts /TopStor/pump.sh addhost.py  /dev/null
            leaderall=` ./etcdget.py leader --prefix `
            leader=`echo $leaderall | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
            leaderip=` ./etcdget.py leader/$leader `
            rm -rf /etc/chrony.conf
            cp /TopStor/chrony.conf /etc/
            sed -i "s/MASTERSERVER/$leaderip/g" /etc/chrony.conf
            systemctl restart chronyd
            echo $perfmon | grep 1 /dev/null
            if [ $? -eq 0 ];
	    then
              /TopStor/queuethis.sh AddingtoOtherleader start system 
            fi
          fi
        done 
        leadername=`./etcdget.py leader --prefix | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
        continue
      fi
    else 
      echo I am not primary.. checking if I am local etcd>> /root/zfspingtmp
newtime=`date +%s`
echo Iamnotprimary $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo I am not primary.. checking if I am local etcd
      netstat -ant | grep 2378 | grep $myip | grep LISTEN >/dev/null
      if [ $? -ne 0 ];
      then
        echo I need to be local etcd .. no etcd is running>> /root/zfspingtmp
newtime=`date +%s`
echo Ineedtobelocal $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo I need to be local etcd .. no etcd is running
        needlocal=1
      else
        echo local etcd is already running>> /root/zfspingtmp
newtime=`date +%s`
echo localetcd $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo local etcd is already running
        needlocal=2
      fi
      echo checking if I am known host >> /root/zfspingtmp
newtime=`date +%s`
echo checkingifiam $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo checking if I am known host
      known=` ./etcdget.py known --prefix 2>/dev/null`
      myconfig=` ./etcdgetlocal.py $myip configured 2>/dev/null`
      echo $known | grep $myhost  >/dev/null
      if [ $? -ne 0 ];
      then
        echo $myconfig | grep yes  >/dev/null
        if [ $? -ne 0 ];
        then
          echo I am not a known and I am not configured. So, adding me as possible >> /root/zfspingtmp
newtime=`date +%s`
echo iamnotaknownnotconfigured $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
          echo I am not a known and I am not configured. So, adding me as possible
          ./etcdput.py possible$myhost $myip  
        else
          echo I am not a known but I am configured so need to activate >> /root/zfspingtmp
newtime=`date +%s`
echo iamnotaknownbutconfigured $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
          echo I am not a known but I am configured so need to activate
          ./etcdput.py toactivate$myhost $myip  
        fi 
      else
        echo $perfmon | grep 1 >/dev/null
        if [ $? -eq 0 ];
        then
          /TopStor/queuethis.sh iamkknown start system 
        fi
        echo I am known so running all needed etcd task:boradcast,isknown:$isknown >> /root/zfspingtmp
newtime=`date +%s`
echo iamknown $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo I am known so running all needed etcd task:boradcast,isknown:$isknown
        if [[ $isknown -eq 0 ]];
        then
          echo running sendhost.py $leaderip 'user' 'recvreq' $myhost >>/root/tmp2
newtime=`date +%s`
echo sendhostleader $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
          echo running sendhost.py $leaderip 'user' 'recvreq' $myhost 
          leaderall=` ./etcdget.py leader --prefix `
          leader=`echo $leaderall | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
          leaderip=`echo $leaderall | awk -F"')" '{print $1}' | awk -F", '" '{print $2}'`
          /pace/etcdsync.py $myip pools pools >/dev/null
          /pace/etcdsync.py $myip poolsnxt poolsnxt >/dev/null
          /pace/etcdsync.py $myip nextlead nextlead >/dev/null
          /pace/sendhost.py $leaderip 'logall' 'recvreq' $myhost  >/dev/null 
          isknown=$((isknown+1))
newtime=`date +%s`
echo finishrunning sendhost  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        fi
        if [[ $isknown -le 10 ]];
        then
          isknown=$((isknown+1))
        fi
        if [[ $isknown -eq 3 ]];
        then
newtime=`date +%s`
echo isknowneq3  $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
          /pace/etcdput.py ready/$myhost $myip 
          /pace/etcdput.py ActivePartners/$myhost $myip 
          /TopStor/broadcast.py SyncHosts /TopStor/pump.sh addhost.py >/dev/null
          touch /pacedata/addiscsitargets 
          ./etcddel.py toimport/$myhost >/dev/null 
          toimport=1
        fi
        echo finish running tasks task:boradcast, log..etc >> /root/zfspingtmp
newtime=`date +%s`
echo finishrunningtasks $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
        echo finish running tasks task:boradcast, log..etc 
        echo $perfmon | grep 1 >/dev/null
        if [ $? -eq 0 ];
        then
          /TopStor/queuethis.sh iamkknown stop system 
        fi
      fi
    fi
  fi 
  echo $perfmon | grep 1 >/dev/null
  if [ $? -eq 0 ];
  then
    /TopStor/queuethis.sh AmIprimary stop system 
  fi
newtime=`date +%s`
echo running putzpool 3 $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo $lsscsiflag | grep putzpool
  if [ $? -eq 0 ];
  then
   pgrep putzpool 
   if [ $? -ne 0 ];
   then
    /pace/putzpool.py 3 $isprimary $primtostd > /dev/null 
    /TopStor/HostgetIPs	>/dev/null 
    lsscsiflag=`echo $lsscsiflag | sed 's/putzpool/init/g'`
   fi
  fi
  echo checking if I need to run local etcd >> /root/zfspingtmp
newtime=`date +%s`
echo checkingifIneedlocal $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo checking if I need to run local etcd 
  if [ $needlocal -eq 1 ];
  then
    echo $perfmon | grep 1 >/dev/null
    if [ $? -eq 0 ];
    then
      /TopStor/queuethis.sh IamLocal start system 
    fi
    echo start the local etcd >> /root/zfspingtmp
newtime=`date +%s`
echo starttheocal $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo start the local etcd 
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
    ./etcdsync.py $myip primary primary >/dev/null 
    ./etcddellocal.py $myip known --prefix >/dev/null 
    ./etcddellocal.py $myip localrun --prefix >/dev/null 
    ./etcddellocal.py $myip run --prefix >/dev/null 
    ./etcdsync.py $myip known known >/dev/null 
    ./etcdsync.py $myip localrun localrun >/dev/null 
    ./etcdsync.py $myip leader known >/dev/null 
    echo done and exit >> /root/zfspingtmp
newtime=`date +%s`
echo doneandexit $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo done and exit 
    echo $perfmon | grep 1 >/dev/null
    if [ $? -eq 0 ]; then
      /TopStor/queuethis.sh IamLocal stop system 
    fi
    continue 
  fi
  if [ $needlocal -eq  2 ];
  then
    echo I am already local etcd running iscsirefresh on $myip $myhost  >> /root/zfspingtmp
newtime=`date +%s`
echo Iamalreadylocal $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo I am already local etcd running iscsirefresh on $myip $myhost 
    pgrep iscsiwatchdog
    if [ $? -ne 0 ];
    then
      /pace/iscsiwatchdog.sh nodisk $myhost $leader $myip >/dev/null
    fi
  fi
  echo checking if still in the start initcron is still running  >> /root/zfspingtmp
newtime=`date +%s`
echo stilininitcron? $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo checking if still in the start initcron is still running 
  if [ -f /pacedata/forzfsping ];
  then
    echo Yes. so I have to exit >> /root/zfspingtmp
newtime=`date +%s`
echo yesstill $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo Yes. so I have to exit 
    continue
  fi
  cd /pace
  echo No then Checking Node Evacuation >> /root/zfspingtmp
newtime=`date +%s`
echo nosocheckingevacuation $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo No then Checking Node Evacuation
  pgrep Evacuatelocal
  if [ $? -ne 0 ];
  then
    /TopStor/Evacuatelocal.py >/dev/null
    cd /pace
  fi
  echo Checking  I am primary >> /root/zfspingtmp
newtime=`date +%s`
echo checkprimary $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo Checking  I am primary
  if [ $runningcluster -eq 1 ];
  then
    echo Yes I am primary so will check for known hosts >> /root/zfspingtmp
newtime=`date +%s`
echo YesIamprimary $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    echo Yes I am primary so will check for known hosts
    pgrep  remknown 
    if [ $? -ne 0 ];
    then
      ./remknown.py $myhost >/dev/null  
    fi
newtime=`date +%s`
echo finished remknown $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    pgrep  addknown 
    if [ $? -ne 0 ];
    then
      ./addknown.py $myhost >/dev/null  
    fi
newtime=`date +%s`
echo finished addknown $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    pgrep addactive 
    if [ $? -ne 0 ];
    then
      ./addactive.py $myhost >/dev/null  
    fi
newtime=`date +%s`
echo finished addactive $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    pgrep  selectimport 
    if [ $? -ne 0 ];
    then
      echo /TopStor/selectimport.py $myhost 
      /TopStor/selectimport.py $myhost >/dev/null 
    fi
newtime=`date +%s`
echo finished selectimport $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  fi 
  echo toimport = $toimport >> /root/zfspingtmp
newtime=`date +%s`
echo toimport $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo toimport = $toimport 
  if [ $toimport -gt 0 ];
  then
    mytoimport=`ETCDCTL_API=3 /pace/etcdget.py toimport/$myhost`
    if [ $mytoimport == '-1' ];
    then 
      echo Yes  I have no record in toimport/$myhost even no nothing=$mytoimport >> /root/zfspingtmp
newtime=`date +%s`
echo YesIahavenorrecord $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo Yes  I have no record in toimport/$myhost even no nothing=$mytoimport
    fi
    echo $mytoimport | grep nothing >/dev/null
    if [ $? -eq 0 ];
    then
      echo it is nothing , toimport=$toimport >> /root/zfspingtmp
newtime=`date +%s`
echo itisnothing $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo it is nothing , toimport=$toimport
      if [ $toimport -eq 1 ];
      then
        if [ $leaderfail -eq 0 ];
        then
          /TopStor/logmsg.py Partsu04 info system $myhost $myip 
          ./etcddel.py cann --prefix >/dev/null 
        else
          leaderfail=0
        fi
      fi
      if [ $toimport -eq 2 ];
      then
        if [ $leaderfail -eq 0 ];
        then
          /TopStor/logmsg.py Partsu03 info system $myhost $myip 
          ./etcddel.py cann --prefix >/dev/null 
        else
          leaderfail=0
        fi
      fi
      if [ $toimport -eq 3 ];
      then
        /TopStor/logmsg.py Partsu06 info system 
      fi
      toimport=0
      oldclocker=$clocker
    else
      echo checking zpool to import>> /root/zfspingtmp
newtime=`date +%s`
echo checkingzpool $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      echo checking zpool to import
      echo $lsscsiflag | grep zpooltoimport
      if [ $? -eq 0 ];
      then
       pgrep zpooltoimport
       if [ $? -ne 0 ];
       then
        lsscsiflag=$lsscsiflag'putzpool'
        /pace/iscsiwatchdog.sh adddisk  $myhost $leader >/dev/null
        /TopStor/zpooltoimport.py all >/dev/null
        lsscsicount=$((lsscsicount+1))
        if [ lsscsicount -ge 1 ];
        then
         oldlsscsi=$lsscsi
	 lsscsicount=0
	 lsscsiflag='putzpool'
        fi
       fi
      fi
newtime=`date +%s`
echo beforeVolumeCheck $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
      pgrep  VolumeCheck 
      if [ $? -ne 0 ];
      then
        /TopStor/VolumeCheck >/dev/null 
      fi
newtime=`date +%s`
echo afterVolumeCheck $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
    fi
  fi
  if [ $toimport -eq 0 ];
  then
    clocker=`date +%s`
    clockdiff=$((clocker-oldclocker))
  fi
  echo Clockdiff = $clockdiff >> /root/zfspingtmp
newtime=`date +%s`
echo Clockdiff $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo Clockdiff = $clockdiff 
  if [ $clockdiff -ge 500 ];
  then
    ./etcddel.py toimport/$myhost >/dev/null 
    /TopStor/logmsg.py Partst06 info system  
    toimport=3
    oldclocker=$clocker
    clockdiff=0
  fi
  pgrep iscsiwatchdog
  if [ $? -ne 0 ];
  then
    /pace/iscsiwatchdog.sh nodisk  $myhost $leader $myip >/dev/null
  fi
  echo Collecting a change in system occured >> /root/zfspingtmp
newtime=`date +%s`
echo Collecingachange $((newtime-basetime)) total=$((newtime-origtime))>> /root/zfspingtiming
basetime=$newtime
  echo Collecting a change in system occured 
  pgrep  changeop 
  if [ $? -ne 0 ];
  then
    ETCDCTL_API=3 /pace/changeop.py $myhost >/dev/null 
  fi
  pgrep  selectspare 
  if [ $? -ne 0 ];
  then
    ETCDCTL_API=3 /pace/selectspare.py $myhost >/dev/null 
  fi
done
