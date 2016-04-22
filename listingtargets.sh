iscsimapping='/pace/iscsimapping'
myhost=`hostname`;
iscsitargets='/pace/iscsitargets';
declare -a hosts=(`cat $iscsitargets | grep -v "$myhost" | awk '{print $2}'`);
declare -a alldevdisk=();
i=0;
rm -r $iscsimapping 2>/dev/null
for host in "${hosts[@]}"; do
 alldevdisk=(`ls -l /dev/disk/by-path/ | grep "$host"  | grep -v part | awk -F'-> ' '{print $2}'`)
 for devdisk in "${alldevdisk[@]}"; do
  diskid=`ls -l /dev/disk/by-id/ | grep "$devdisk" | grep scsi | grep -v part | awk -F'scsi-' '{print $2}' | awk -F' ->' '{print $1}'`
  devformatted='/dev/s'`echo $devdisk | awk -F's' '{print $2}'`
  if [ -z $diskid ]; then
   echo "$host" notconnected >> $iscsimapping;
  else
   echo "$host" $devformatted $diskid >> $iscsimapping;
  fi
 done;
 i=$((i+1));
done

