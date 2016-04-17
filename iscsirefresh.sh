cd /pace
iscsimapping='/pace/iscsimapping';
while read -r  hostline ; do
 echo $hostline | grep notconnected >/dev/null
 host=`echo $hostline | awk '{print $1}'`
 ping -c 1 -W 1 $host &>/dev/null
 if [ $? -eq 0 ]; then
  hostpath=`ls /var/lib/iscsi/nodes | grep "$host"`;
  rm -rf /var/lib/iscsi/nodes/$hostpath &>/dev/null
  hostiqn=`/sbin/iscsiadm -m discovery --portal $host --type sendtargets | awk '{print $2}'`
  /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -u
  /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -l
 fi
done < $iscsimapping
sleep 2;
