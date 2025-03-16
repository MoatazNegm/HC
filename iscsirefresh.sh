#!/usr/bin/sh

etcdip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
cd /pace
sessions='sessions'`/sbin/iscsiadm -m session --rescan 2>/dev/null`
needrescan=0;
#mycluster=`nmcli conn show mycluster | grep ipv4.addresses | awk '{print $2}' | awk -F'/' '{print $1}'`
nodes=(`docker exec etcdclient /TopStor/etcdget.py $etcdip ready --prefix | awk -F"', " '{print $2}' | awk -F"'" '{print $2}'`)
#nodes=(`docker exec etcdclient /TopStor/etcdgetlocal.py ready --prefix | awk -F'Partners/' '{print $2}' | awk -F"'" '{print $1}'`)
for host in "${nodes[@]}" ; do
 echo $sessions  | grep ${host},
 if [ $? -ne 0 ]; then
  echo sessions=$sessions
  needrescan=1;
  #hostpath=`ls /var/lib/iscsi/nodes/ | grep "$host"`;
  echo '#############################################################'
  echo /sbin/iscsiadm -m discovery --portal ${host}:3266 --type sendtargets 2\>\/dev\/null \| grep $host \| awk \'{print \$2}\'
  hostiqn=`/sbin/iscsiadm -m discovery --portal ${host}:3266 --type sendtargets 2>/dev/null | grep $host | awk '{print $2}'`
  echo hostiqn=$hostiqn
  echo /sbin/iscsiadm -m node --targetname $hostiqn --portal ${host}:3266 -u 2\>\/dev\/null
  /sbin/iscsiadm -m node --targetname $hostiqn --portal ${host}:3266 -u 2>/dev/null
  echo /sbin/iscsiadm -m node --targetname $hostiqn --portal ${host}:3266 -l
  /sbin/iscsiadm -m node --targetname $hostiqn --portal ${host}:3266 -l
  fi
done
