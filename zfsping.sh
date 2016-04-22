cd /pace
iscsimapping='/pace/iscsimapping';
cp ${iscsimapping} ${iscsimapping}new;
declare -a pools=(`/sbin/zpool list -H | awk '{print $1}'`)
declare -a idledisk=("hi,world");
runninghosts=`cat $iscsimapping | grep -v notconnected`
newrunninghosts=`cat $iscsimapping | grep -v notconnected`
declare -a deadhosts=(`cat $iscsimapping | grep  notconnected`)
newdeadhosts=`cat $iscsimapping | grep  notconnected`
dirty=0;
singledisk=`/sbin/zpool list -Hv $pool | wc -l`
if [ $singledisk -gt 2 ]; then
 for pool in "${pools[@]}"; do
  /sbin/zpool clear p1 &>/dev/null
  /sbin/zpool status $pool | grep "was /dev" &>/dev/null
  if [ $? -eq 0 ]; then
   faildisk=`/sbin/zpool status $pool | grep "was /dev" | awk -F'-id/' '{print $2}' | awk -F'-part' '{print $1}'`;
   /sbin/zpool detach $pool $faildisk &>/dev/null;
  fi 
  if [ $? -eq 0 ]; then
   faildisk=`/sbin/zpool status $pool | grep "was /dev/s" | awk -F'was ' '{print $2}'`;
   /sbin/zpool detach $pool $faildisk &>/dev/null;
  fi 
  /sbin/zpool status $pool | grep OFFLINE &>/dev/null
  /sbin/zpool status $pool | grep OFFLINE &>/dev/null
  if [ $? -eq 0 ]; then
   faildisk=`/sbin/zpool status $pool | grep OFFLINE | awk '{print $1}'`;
   /sbin/zpool detach $pool $faildisk &>/dev/null;
  fi
  /sbin/zpool status $pool | grep UNAVAIL &>/dev/null
  if [ $? -eq 0 ]; then
   faildisk=`/sbin/zpool status $pool | grep UNAVAIL | awk '{print $1}'`;
   /sbin/zpool detach $pool $faildisk &>/dev/null;
  fi 
 done
fi

while read -r  hostline ; do
 host=`echo $hostline | awk '{print $1}'`
 ping -c 1 -W 1 $host &>/dev/null; 
 if [ $? -ne 0 ]; then
   hostdiskid=`echo $hostline | awk '{print $3}'`
   for pool in "${pools[@]}"; do
    /sbin/zpool list -Hv $pool | grep "$hostdiskid" &>/dev/null
    if [ $? -eq 0 ]; then 
     /sbin/zpool offline $pool scsi-"$hostdiskid" &>/dev/null;
    fi
   done;
   sed -i "/$host/d"  ${iscsimapping}new ; 
   echo $host notconnected >> ${iscsimapping}new;
#  fi
 else
#  host=`echo $hostline | awk '{print $1}'`
#  ping -c 1 -W 1 $host &>/dev/null/
#  if [ $? -eq 0 ]; then
  ls -l /dev/disk/by-path/ | grep "$host" &>/dev/null
  if [ $? -ne 0 ]; then
   hostpath=`ls /var/lib/iscsi/nodes | grep "$host"`
   rm -rf /var/lib/iscsi/nodes/$hostpath &>/dev/null
   /sbin/iscsiadm -m discovery --type sendtargets --portal $host &>/dev/null
  hostiqn=`/sbin/iscsiadm -m discovery --portal $host --type sendtargets | awk '{print $2}'`
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -u &>/dev/null
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -l &>/dev/null
  sleep 2
  fi
  devdisk=`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk -F'->' '{print $2}'`;
  devformatted=`echo $devdisk | awk -F's' '{print $2}'`;
  newdiskid=`ls -l /dev/disk/by-id/ | grep "$devdisk" | grep -v part | grep scsi | awk -F'scsi-' '{print $2}' | awk -F' ->' '{print $1}'`;
  sed -i "/$host/d"  ${iscsimapping}new ; 
  echo $host "s"$devformatted $newdiskid >> ${iscsimapping}new;
  /sbin/zpool list -vH | grep $newdiskid &>/dev/null
  if [ $? -ne 0 ]; then 
   idledisk=("${idledisk[@]}" "$host,$newdiskid");
  fi
  echo ${idledisk[@]}
 fi
# fi
done < $iscsimapping
if [ "${#idledisk[@]}" -gt 1 ]; then
 for pool in "${pools[@]}"; do
  singledisk=`/sbin/zpool list -Hv $pool | wc -l`
  if [ $singledisk -le 2 ]; then
   /sbin/zpool clear $pool &>/dev/null
   runningdisk=`/sbin/zpool list -Hv | grep scsi | awk '{print $1}'`;
   i=$((${#idledisk[@]}-1));
   newdisk=`echo ${idledisk[$i]} | awk -F',' '{print $2}'`
#  dd if=/dev/zero of=/dev/disk/by-id/scsi-"$newdisk" bs=512 count=1 ;
#  sleep 2
#  /sbin/zpool labelclear -f /dev/disk/by-id/scsi-"$newdisk";
#  parted /dev/disk/by-id/scsi-"$newdisk" mklabel msdos;
   /sbin/zpool attach $pool $runningdisk scsi-"$newdisk" ;
   if [ $? -eq 0 ]; then 
#   host=`echo ${idledisk[$i]} | awk -F',' '{print $1}'`
#   devdisk=`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk -F'->' '{print $2}'`;
#   devformatted=`echo $devdisk | awk -F's' '{print $2}'`;
#   sed -i "/$host/d"  ${iscsimapping}new ; 
#   echo $host "s"$devformatted $newdisk >> ${iscsimapping}new;
    unset idledisk[$i];
   fi
  fi 
 done
fi
cp ${iscsimapping}new $iscsimapping
