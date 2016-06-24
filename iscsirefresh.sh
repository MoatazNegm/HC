cd /pace
iscsimapping='/pacedata/iscsimapping';
iscsitargets='/pace/iscsitargets';
#/sbin/iscsiadm -m session --rescan &>/dev/null
needrescan=0;
while read -r  hostline ; do
 host=`echo $hostline | awk '{print $2}'`
 ping -c 1 -W 1 $host &>/dev/null
 if [ $? -eq 0 ]; then
  needrescan=1;
  hostpath=`ls /var/lib/iscsi/nodes/ | grep "$host"`;
  echo cat $iscsimapping  echo $host  grep notconnected 
  cat $iscsimapping |  grep "$host" | grep notconnected &>/dev/null
  if [ $? -eq 0 ]; then
   echo here
   rm -rf /var/lib/iscsi/nodes/send_targets/$host* &>/dev/null
   hostiqn=`/sbin/iscsiadm -m discovery --portal $host --type sendtargets | awk '{print $2}'`
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -u
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -l
  fi
  cat $iscsimapping | grep "$host" &>/dev/null
  if [ $? -ne 0 ]; then
   echo new $host
   hostiqn=`/sbin/iscsiadm -m discovery --portal $host --type sendtargets | awk '{print $2}'`
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -l
  fi
 else
  echo deleteing $host
  rm -rf /var/lib/iscsi/nodes/iqn.2016-03.com.${host}:t1 
  rm -rf /var/lib/iscsi/nodes/${host}* &>/dev/null
 fi
done < $iscsitargets
if [ $needrescan -eq 1 ]; then
# /sbin/iscsiadm -m session --rescan &>/dev/null
 sleep 1; 
fi
sleep 2;
