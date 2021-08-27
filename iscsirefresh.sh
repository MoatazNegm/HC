cd /pace
iscsimapping='/pacedata/iscsimapping';
iscsitargets='/pacedata/iscsitargets';
sessions='sessions'`/sbin/iscsiadm -m session --rescan `
needrescan=0;
myhost=`hostname -s`
hosts=`./etcdget.py ready --prefix | awk -F"', " '{print $2}' | awk -F"'" '{print $2}'`
for host in $hosts ; do
echo I am here $host
 echo $sessions  | grep $host
 if [ $? -ne 0 ]; then
  needrescan=1;
  hostpath=`ls /var/lib/iscsi/nodes/ | grep "$host"`;
  hostiqn=`/sbin/iscsiadm -m discovery --portal $host:3266 --type sendtargets | awk '{print $2}'`
  /sbin/iscsiadm -m node --targetname $hostiqn --portal $host:3266 -u
  /sbin/iscsiadm -m node --targetname $hostiqn --portal $host:3266 -l
  fi
done
sleep 2
