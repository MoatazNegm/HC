#!/usr/bin/sh
cd /pace
iscsimappingorig='/pacedata/iscsimapping'
iscsimapping='/pacedata/iscsimappinglisting'
cp $iscsimappingorig ${iscsimapping}old
rm -rf $iscsimapping 2>/dev/null
etcdip=`echo $@ | awk '{print $1}'`
iscsitargets='/pacedata/iscsitargets';
#declare -a hosts=(`cat $iscsitargets |  awk '{print $2}'`);
declare -a hosts=(`docker exec etcdclient /pace/iscsiclients.py $etcdip | grep target | awk -F'/' '{print $2}'`);

declare -a alldevdisk=();
declare -a hostline=();
diskstatus='free'
i=0;
for host in "${hosts[@]}"; do
 ls /var/lib/iscsi/nodes/  | grep  "$host" &>/dev/null
 if [ $? -ne 0 ] ; then
  cat ${iscsimapping}old | grep "$host" &>/dev/null
  if [ $? -ne 0 ]; then
   echo $host null null notconnected >> ${iscsimapping};
  else
   while read -r hostline; do
    echo $hostline | grep $host
    if [ $? -eq 0 ]; then
     theline=`echo $hostline | awk '{$4=""; print }'`;
     echo $theline notconnected >> ${iscsimapping};
    fi
   done < ${iscsimapping}old
  fi
  cd /pacedata/pools/ 2>/dev/null
  rm -rf $( ls /pacedata/pools/* | grep "$host") &>/dev/null
  cd /pace
 else
  sesid=`/sbin/iscsiadm -m node | grep $host | awk '{print $1}' | awk -F',' '{print $2}'`
  sesinfo=`/sbin/iscsiadm -m session -r $sesid -P 3 | grep Lun | awk -F'csi' '{print $2}' | awk '{print $1}' | head -1`
  #alldevdisk=(`ls -l /dev/disk/by-path/ | grep  "$host"  | grep -v part | grep -v wwn | awk '{print $11}'`)
  alldevdisk=(`lsblk -Sn | grep ${sesinfo}\: | awk '{print $1}'`)
  echo alldev=${alldevdisk[@]}
  alldev2=`/sbin/zpool status >/dev/null | grep scsi | awk '{print $1" "$2}'`
  for devdisk in "${alldevdisk[@]}"; do
    diskstatus='free'
#   diskid=`ls -l /dev/disk/by-id/ | grep  "$devdisk" | grep -v wwn | grep -v part | awk '{print $9}'`
   echo devdisk=$devdisk
   diskid='scsi-3'`lsblk -Sn -o name,serial | grep "$devdisk" | awk '{print $2}'`
   devformatted='/dev/'$devdisk 
   alphadisk=$devdisk
   disksize=`lsblk -b | grep -w "$alphadisk" | awk '{print $4}'`
   diskgiga=$(($disksize/1000/1000/1000));
   diskstatus=`echo "${alldev2[@]}" | grep $diskid | awk '{print $2}'`
   if [ -z $diskstatus ]; then
    diskstatus="free"
   fi
   echo $diskstatus | grep 'OFFL' 
   if [ $? -ne 0 ]; then
    echo "$host" $devformatted $diskid $diskgiga $diskstatus >> $iscsimapping;
   fi
  done;
  /pace/diskstatus.py $host >> $iscsimapping;
  i=$((i+1));
 fi
done

cp $iscsimapping $iscsimappingorig 
