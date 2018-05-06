#!/usr/bin/sh
cd /pace
ps -ef |grep startzfs.sh | grep -v tty | grep -v grep 
if [ $? -eq 0 ];
then
 exit
fi
myip=`pcs resource show CC | grep Attribute | awk '{print $2}' | awk -F'=' '{print $2 }'`
myhost=`hostname -s`
runningcluster=0
#systemctl status etcd &>/dev/null
cat /etc/etcd/etcd.conf.yml | grep 2379
if [ $? -eq 0 ];
then
 runningcluster=1
 leader='"'`ETCDCTL_API=3 ./etcdget.py leader --prefix`'"'
 echo $leader | grep '""' &>/dev/null
 if [ $? -eq 0 ]; 
 then
  ETCDCTL_API=3 ./runningetcdnodes.py $myip &>/dev/null
  ETCDCTL_API=3 ./etcdput.py leader$myhost $myip &>/dev/null
 fi
 ETCDCTL_API=3 ./addknown.py &>/dev/null
 ETCDCTL_API=3 ./allconfirmed.py &>/dev/null
 ETCDCTL_API=3 ./broadcastlog.py &>/dev/null
 ETCDCTL_API=3 ./receivelog.py &>/dev/null
else
 leader=`ETCDCTL_API=3 ./etcdget.py leader --prefix 2>&1`
 echo $leader | grep Error  &>/dev/null
 if [ $? -eq 0 ];
 then
  clusterip=`cat /pacedata/clusterip`
  systemctl stop etcd
  ./etccluster.py 'new'
  systemctl daemon-reload;
  systemctl start etcd;
  ETCDCTL_API=3 ./etcdput.py clusterip $clusterip &>/dev/null
  pcs resource create clusterip ocf:heartbeat:IPaddr nic="$enpdev" ip=$clusterip cidr_netmask=24;
  ETCDCTL_API=3 ./runningetcdnodes.py $myip &>/dev/null
  ETCDCTL_API=3 ./etcdput.py leader$myhost $myip &>/dev/null
  /sbin/zpool import -a &>/dev/null
  ETCDCTL_API=3 ./putzpool.py &>/dev/null
  systemctl start nfs
  chgrp apache /var/www/html/des20/Data/*
  chmod g+r /var/www/html/des20/Data/*
  runningcluster=1
 else 
  ETCDCTL_API=3 ./etcdget.py clusterip > /pacedata/clusterip 
  known=`ETCDCTL_API=3 ./etcdget.py known --prefix 2>&1`
  echo $known | grep $myhost  &>/dev/null
  if [ $? -ne 0 ];
  then
   ETCDCTL_API=3 ./etcdput.py possible$myhost $myip &>/dev/null
  else
   ETCDCTL_API=3 ./changeetcd.py &>/dev/null
   ETCDCTL_API=3 ./receivelog.py &>/dev/null
   ETCDCTL_API=3 ./broadcastlog.py &>/dev/null
  fi
 fi 
fi
#sh iscsirefresh.sh   &>/dev/null &
#sh listingtargets.sh  &>/dev/null
#./addtargetdisks.sh
echo $runningcluster | grep 1 &>/dev/null
if [ $? -eq 0 ];
then
 lsscsi=`lsscsi -i --size | md5sum`
 lsscsiold=`ETCDCTL_API=3 /pace/etcdget.py checks/$myhost/lsscsi `
 echo $lsscsi | grep $lsscsiold &>/dev/null
 if [ $? -eq 0 ];
 then
  zpool1=`/sbin/zpool status 2>/dev/null | md5sum| awk '{print $1}'`
  zpool1old=`ETCDCTL_API=3 /pace/etcdget.py checks/$myhost/zpool `
  echo $zpool1 | grep $zpool1old &>/dev/null
  if [ $? -eq 0 ];
  then 
   exit
  fi
 fi
fi
hostnam=`cat /TopStordata/hostname`
declare -a pools=(`/sbin/zpool list -H | awk '{print $1}'`)
declare -a idledisk=();
declare -a hostdisk=();
declare -a alldevdisk=();
cd /pace
/sbin/fdisk -l 2>&1 | grep "cannot open" &>/dev/null
if [ $? -eq 0 ];
then
 faileddisk=`/sbin/fdisk -l 2>&1 | grep "cannot open" | awk '{print $4}' | awk -F':' '{print $1}' | awk -F'/' '{print $3}'`
 echo "offline" > /sys/block/$faileddisk/device/state
 echo "1" > /sys/block/$faileddisk/device/delete
 sleep 2
 /bin/systemctl restart target
else
 /bin/targetcli ls &>/dev/null
 if [ $? -ne 0 ];
 then
  /bin/systemctl restart target
  /bin/targetcli saveconfig
 fi
fi
ids=`/bin/lsblk -Sn -o serial`
if [ ! -z $pools ];
then
 for pool in "${pools[@]}"; do
  spares=(`/sbin/zpool status $pool | grep scsi | grep -v OFFLINE | awk '{print $1}'`)  
  for spare in "${spares[@]}"; do
   echo $ids | grep ${spare:8} &>/dev/null
   if [ $? -ne 0 ]; then
    diskid=`/bin/python3.6 diskinfo.py /pacedata/disklist.txt $spare`
    /TopStor/logmsg.sh Diwa4 warning system $diskid $hostnam
    zpool remove $pool $spare;
    if [ $? -eq 0 ]; then
     /TopStor/logmsg.sh Disu4 info system $diskid $hostnam 
     cachestate=1
    else 
     /TopStor/logmsg.sh Dist5 info system $diskid  $hostnam
    zpool offline $pool $spare
    /TopStor/logmsg.sh Disu5 info system $diskid $hostnam 
    fi
   fi
  done 
 done
 for pool in "${pools[@]}"; do
  singledisk=`/sbin/zpool list -Hv $pool | wc -l`
  zpool=`/sbin/zpool status $pool`
  if [ $singledisk -gt 3 ]; then
   echo "${zpool[@]}" | grep -E "FAULT|OFFLI" &>/dev/null
   if [ $? -eq 0 ];
   then
    ETCDCTL_API=3 /pace/etcddel.py run/$myhost --prefix &>/dev/null
    ETCDCTL_API=3 /pace/putzpool.py run/$myhost --prefix &>/dev/null
    faildisk=`echo "${zpool[@]}" | grep -E "FAULT|OFFLI" | awk '{print $1}'`
    diskpath=`ETCDCTL_API=3 /pace/diskinfo.py run getkey $faildisk `
    diskidf=`echo $diskpath | awk -F'/' '{print $(NF-1)}'`
    ETCDCTL_API=3 /pace/diskinfo.py run getkey $diskpath | awk -F'/' '{print $(NF-1)}'
    /TopStor/logmsg.sh Difa1 error system $diskidf $hostnam
    sparedisk=`echo "${zpool[@]}" | grep "AVAIL" | awk '{print $1}' | head -1`
    sparedisk=`echo "${zpool[@]}" | grep "AVAIL" | awk '{print $1}' | head -1`
    if [ ! -z $sparedisk ]; then
     diskids=`ETCDCTL_API=3 /pace/diskinfo.py run getkey $sparedisk | awk -F'/' '{print $(NF-1)}'`
     /TopStor/logmsg.sh Dist2 info system $diskidf $diskids $hostnam
     /sbin/zpool offline $pool $faildisk
     /sbin/zpool replace $pool $faildisk $sparedisk
     /TopStor/logmsg.sh Disu2 info system $diskidf $diskidf $hostnam
     /TopStor/logmsg.sh Dist3 info system $diskidf $hostnam
     /sbin/zpool detach $pool $faildisk &>/dev/null;
     /TopStor/logmsg.sh Disu3 info system $diskidf $hostnam
     ETCDCTL_API=3 /pace/etcddel.py run/$myhost --prefix &>/dev/null
     ETCDCTL_API=3 /pace/putzpool.py run/$myhost --prefix &>/dev/null
    fi
    diskstatus=`echo $diskpath | awk -F'/' '{OFS=FS;$NF=""; print}' `'status'
    diskfs=`ETCDCTL_API=3 /pace/diskinfo.py run getvalue $diskstatus `
    echo $diskfs | grep ONLINE &>/dev/null
    if [ $? -eq 0 ];
    then
     ETCDCTL_API=3 ./etcddel.py run/myhost --prefix &>/dev/null
     ETCDCTL_API=3 ./putzpool.py &>/dev/null
    fi
   fi
   /sbin/zpool status $pool | grep "was /dev" &>/dev/null
   if [ $? -eq 0 ]; then
    faildisk=`/sbin/zpool status $pool | grep "was /dev" | awk -F'-id/' '{print $2}' | awk -F'-part' '{print $1}'`;
    /sbin/zpool detach $pool $faildisk &>/dev/null;
    #/sbin/zpool set cachefile=/pacedata/pools/${pool}.cache $pool;
    cachestate=1;
   fi 
   /sbin/zpool status $pool | grep "was /dev/s" ;
   if [ $? -eq 0 ]; then
    faildisk=`/sbin/zpool status $pool | grep "was /dev/s" | awk -F'was ' '{print $2}'`;
    /sbin/zpool detach $pool $faildisk &>/dev/null;
    #/sbin/zpool set cachefile=/pacedata/pools/${pool}.cache $pool ;
    cachestate=1;
   fi 
   /sbin/zpool status $pool | grep UNAVAIL &>/dev/null
   if [ $? -eq 0 ]; then
    faildisk=`/sbin/zpool status $pool | grep UNAVAIL | awk '{print $1}'`;
    /sbin/zpool detach $pool $faildisk &>/dev/null;
    #/sbin/zpool set cachefile=/pacedata/pools/${pool}.cache $pool;
    cachestate=1;
   fi 
  fi
 done
 zpool1=`/sbin/zpool status 2>/dev/null | md5sum | awk '{print $1}'`
 ETCDCTL_API=3 /pace/etcdput.py checks/$myhost/zpool $zpool1 &>/dev/null
fi
# ETCDCTL_API=3 /pace/etcddel.py run/$myhost --prefix &>/dev/null
# ETCDCTL_API=3 /pace/putzpool.py run/$myhost --prefix &>/dev/null
# zpool1=`/sbin/zpool status 2>/dev/null | md5sum | awk '{print $1}'`
# ETCDCTL_API=3 /pace/etcdput.py checks/$myhost/zpool $zpool1 &>/dev/null
 lsscsi=`lsscsi -i --size | md5sum | awk '{print $1}'`
 ETCDCTL_API=3 /pace/etcdput.py checks/$myhost/lsscsi $lsscsi  &>/dev/null
