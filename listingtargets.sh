iscsimapping='/pacedata/iscsimapping'
myhost=`hostname`;
iscsitargets='/pacedata/iscsitargets';
declare -a hosts=(`cat $iscsitargets |  awk '{print $2}'`);
declare -a alldevdisk=();
declare -a hostline=();
i=0;
cp $iscsimapping ${iscsimapping}old
rm -r $iscsimapping 2>/dev/null
for host in "${hosts[@]}"; do
 ls /var/lib/iscsi/nodes/  | grep  "$host" &>/dev/null
 if [ $? -ne 0 ] ; then
  cat ${iscsimapping}old | grep "$host" &>/dev/null
  if [ $? -ne 0 ]; then
   echo $host null null notconnected >> ${iscsimapping};
   echo $host
  else
   while read -r hostline; do
    echo $hostline | grep $host
    if [ $? -eq 0 ]; then
     theline=`echo $hostline | awk '{$4=""; print }'`;
     echo $theline notconnected >> ${iscsimapping};
    fi
   done < ${iscsimapping}old
  fi
  cd /pacedata
  rm -rf $( ls /pacedata/ | grep "$host") &>/dev/null
  cd /pace
 else
  alldevdisk=(`ls -l /dev/disk/by-path/ | grep  "$host"  | grep -v part | grep -v wwn | awk '{print $11}'`)
  for devdisk in "${alldevdisk[@]}"; do
   diskid=`ls -l /dev/disk/by-id/ | grep  "$devdisk" | grep -v wwn | grep -v part | awk '{print $9}'`
   devformatted='/dev/'`echo $devdisk | awk -F'/' '{print $3}'`
   if [ -z $diskid ]; then
    echo "$host" null null notconnected >> $iscsimapping;
   else
    echo "$host" $devformatted $diskid >> $iscsimapping;
   fi
  done;
  i=$((i+1));
 fi
done

