iscsimapping='/pacedata/iscsimapping'
myhost=`hostname`;
iscsitargets='/pacedata/iscsitargets';
declare -a hosts=(`cat $iscsitargets |  awk '{print $2}'`);
declare -a alldevdisk=();
i=0;
rm -r $iscsimapping 2>/dev/null
for host in "${hosts[@]}"; do
 ls /var/lib/iscsi/nodes/  | grep  "$host" &>/dev/null
 if [ $? -ne 0 ] ; then
  echo "$host" notconnected >> $iscsimapping;
  cd /pacedata
  rm -rf $( ls /pacedata/ | grep "$host") &>/dev/null
  cd /pace
 else
  alldevdisk=(`ls -l /dev/disk/by-path/ | grep  "$host"  | grep -v part | grep -v wwn | awk '{print $11}'`)
  for devdisk in "${alldevdisk[@]}"; do
   diskid=`ls -l /dev/disk/by-id/ | grep  "$devdisk" | grep -v wwn | grep -v part | awk '{print $9}'`
   devformatted='/dev/'`echo $devdisk | awk -F'/' '{print $3}'`
   if [ -z $diskid ]; then
    echo "$host" notconnected >> $iscsimapping;
   else
    echo "$host" $devformatted $diskid >> $iscsimapping;
   fi
  done;
  i=$((i+1));
 fi
done

