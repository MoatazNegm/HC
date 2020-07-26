#!/bin/sh
export PATH=/bin:/usr/bin:/sbin:/usr/sbin:/root
myhost=`hostname -s `
thehost=`echo $@ | awk '{print $1}'`
#declare -a disks=(`lsscsi -i | grep $thehost | awk '{print $6" "$7}'`);
./etcddel.py pool $thehost
./etcddel.py vol $thehost
./etcdput.py tosync yes 
declare -a disks=`lsscsi -i | grep $thehost | awk '{print $6" "$7}'`;
echo "${disks[@]}"
echo $@ > /root/losthostparam
echo "${disks[@]}" > /root/losthost
echo pdisks=` echo "${disks[@]}" | awk '{print $1}' | awk -F'/' '{print $NF}' `
echo pdisks="${pdisks[@]}" >> /root/losthost
echo  "${disks[@]}" | while read l;
do
   echo echo l=$l  >> /root/hostlost
   dis=`echo $l | awk '{print $1}'  | awk -F'/' '{print $3}'`
   echo 1 > /sys/block/$dis/device/delete 2>/dev/null
   echo echo 1 \> /sys/block/$dis/device/delete >> /root/hostlost
done
echo disks="${disks[@]}" >> /root/hostlosttmp
echo "${disks[@]}" | awk '{print $2}'  | while read l;
do
 echo checking disk $l >> /root/hostlosttmp
 ETCDCTL_API=3 /pace/changeop.py $myhost scsi-$l 
done
echo udpating database >> /root/hostlosttmp
#ETCDCTL_API=3 /pace/etcdget.py pools --prefix | grep "\/$thehost" | grep "\/${myhost}" > /TopStordata/forlocalpools
ETCDCTL_API=3 /pace/etcddel.py known/$thehost  --prefix
ETCDCTL_API=3 /pace/importlocalpools.py $myhost $thehost 
ETCDCTL_API=3 /pace/etcddel.py hosts/$thehost  --prefix
ETCDCTL_API=3 /pace/etcddel.py prop/$thehost
ETCDCTL_API=3 /pace/etcdput.py losthost/$thehost `date +%s` 
ETCDCTL_API=3 /pace/etcddel.py cannot  --prefix
#ETCDCTL_API=3 /pace/etcddel.py pools $thehost
ETCDCTL_API=3 /pace/etcddel.py oldhosts/$thehost  --prefix
ETCDCTL_API=3 /TopStor/broadcast.py SyncHosts /TopStor/pump.sh addhost.py
ETCDCTL_API=3 /pace/putzpool.py 
echo  it is done >> /root/hostlosttmp

