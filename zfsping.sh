#!/usr/bin/sh
cd /pace
ps -ef |grep startzfs.sh | grep -v tty | grep -v grep 
if [ $? -eq 0 ];
then
 echo here??
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
 echo $leader | grep '""'
 if [ $? -eq 0 ]; 
 then
  ETCDCTL_API=3 ./runningetcdnodes.py $myip
  ETCDCTL_API=3 ./etcdput.py leader$myhost $myip
 fi
 ETCDCTL_API=3 ./addknown.py
 ETCDCTL_API=3 ./allconfirmed.py
 ETCDCTL_API=3 ./broadcastlog.py
 ETCDCTL_API=3 ./receivelog.py
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
  ETCDCTL_API=3 ./etcdput.py clusterip $clusterip
  pcs resource create clusterip ocf:heartbeat:IPaddr nic="$enpdev" ip=$clusterip cidr_netmask=24;
  ETCDCTL_API=3 ./runningetcdnodes.py $myip
  ETCDCTL_API=3 ./etcdput.py leader$myhost $myip
  /sbin/zpool import -a
  ETCDCTL_API=3 ./putzpool.py
  systemctl start nfs
  chgrp apache /var/www/html/des20/Data/*
  chmod g+r /var/www/html/des20/Data/*
  runningcluster=1
 else 
  echo checking leader
  ETCDCTL_API=3 ./etcdget.py clusterip > /pacedata/clusterip 
  known=`ETCDCTL_API=3 ./etcdget.py known --prefix 2>&1`
  echo $known | grep $myhost  &>/dev/null
  if [ $? -ne 0 ];
  then
   ETCDCTL_API=3 ./etcdput.py possible$myhost $myip
  else
   ETCDCTL_API=3 ./changeetcd.py
   ETCDCTL_API=3 ./receivelog.py
   ETCDCTL_API=3 ./broadcastlog.py
  fi
 fi 
fi
sh iscsirefresh.sh   &>/dev/null &
sh listingtargets.sh  &>/dev/null
./addtargetdisks.sh
echo $runningcluster | grep 1
if [ $? -eq 0 ];
then
 lsscsi=`lsscsi -i --size | md5sum`
 lsscsiold=`ETCDCTL_API=3 /pace/etcdget.py checks/$myhost/lsscsi `
 echo $lsscsi | grep $lsscsiold
 if [ $? -eq 0 ];
 then
  zpool1=`zpool status | md5sum`
  zpool1old=`ETCDCTL_API=3 /pace/etcdget.py checks/$myhost/zpool `
  echo $zpool1 | grep $zpool1old
  if [ $? -eq 0 ];
  then 
   echo lsscsi no change
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
fdisk -l 2>&1 | grep "cannot open"
if [ $? -eq 0 ];
then
 faileddisk=`fdisk -l 2>&1 | grep "cannot open" | awk '{print $4}' | awk -F':' '{print $1}' | awk -F'/' '{print $3}'`
 echo "offline" > /sys/block/$faileddisk/device/state
 echo "1" > /sys/block/$faileddisk/device/delete
 sleep 2
 systemctl restart target
else
 targetcli ls &>/dev/null
 if [ $? -ne 0 ];
 then
  systemctl restart target
  targetcli saveconfig
 fi
fi
ids=`lsblk -Sn -o serial`
for pool in "${pools[@]}"; do
 spares=(`/sbin/zpool status $pool | grep scsi | grep -v OFFLINE | awk '{print $1}'`)  
 for spare in "${spares[@]}"; do
  echo $ids | grep ${spare:8} &>/dev/null
  if [ $? -ne 0 ]; then
   diskid=`python3.6 diskinfo.py /pacedata/disklist.txt $spare`
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
   ETCDCTL_API=3 /pace/etcddel.py run/$myhost --prefix
   ETCDCTL_API=3 /pace/putzpool.py run/$myhost --prefix
   faildisk=`echo "${zpool[@]}" | grep -E "FAULT|OFFLI" | awk '{print $1}'`
   diskpath=`ETCDCTL_API=3 /pace/diskinfo.py run getkey $faildisk `
   echo $diskpath
   echo faildisk=$faildisk
   diskidf=`echo $diskpath | awk -F'/' '{print $(NF-1)}'`
   echo diskidf=$diskidf
   ETCDCTL_API=3 /pace/diskinfo.py run getkey $diskpath | awk -F'/' '{print $(NF-1)}'
   /TopStor/logmsg.sh Difa1 error system $diskidf $hostnam
   sparedisk=`echo "${zpool[@]}" | grep "AVAIL" | awk '{print $1}' | head -1`
   echo sparedisk=$sparedisk
   sparedisk=`echo "${zpool[@]}" | grep "AVAIL" | awk '{print $1}' | head -1`
   if [ ! -z $sparedisk ]; then
    diskids=`ETCDCTL_API=3 /pace/diskinfo.py run getkey $sparedisk | awk -F'/' '{print $(NF-1)}'`
    echo diskids=$diskids
    /TopStor/logmsg.sh Dist2 info system $diskidf $diskids $hostnam
    echo /sbin/zpool offline $pool $faildisk
    /sbin/zpool offline $pool $faildisk
    echo /sbin/zpool replace $pool $faildisk $sparedisk $hostnam
    /sbin/zpool replace $pool $faildisk $sparedisk
    echo is repalced ?
    /TopStor/logmsg.sh Disu2 info system $diskidf $diskidf $hostnam
    /TopStor/logmsg.sh Dist3 info system $diskidf $hostnam
    /sbin/zpool detach $pool $faildisk &>/dev/null;
    /TopStor/logmsg.sh Disu3 info system $diskidf $hostnam
    ETCDCTL_API=3 /pace/etcddel.py run/$myhost --prefix
    ETCDCTL_API=3 /pace/putzpool.py run/$myhost --prefix
   fi
   diskstatus=`echo $diskpath | awk -F'/' '{OFS=FS;$NF=""; print}' `'status'
   diskfs=`ETCDCTL_API=3 /pace/diskinfo.py run getvalue $diskstatus `
   echo $diskfs | grep ONLINE
   if [ $? -eq 0 ];
   then
    ETCDCTL_API=3 ./etcddel.py run/myhost --prefix
    ETCDCTL_API=3 ./putzpool.py
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
 ETCDCTL_API=3 /pace/etcddel.py run/$myhost --prefix
 ETCDCTL_API=3 /pace/putzpool.py run/$myhost --prefix
 zpool1=`zpool status | md5sum`
 ETCDCTL_API=3 /pace/etcdput.py checks/$myhost/zpool $zpool1 
 lsscsi=`lsscsi -i --size | md5sum`
 ETCDCTL_API=3 /pace/etcdput.py checks/$myhost/lsscsi $lsscsi 
