cd /pace
iscsimapping='/pace/iscsimapping';
declare -a pools=(`/sbin/zpool list -H | awk '{print $1}'`)
declare -a idledisk=("hi,world");

while read -r  hostline ; do
 host=`echo $hostline | awk '{print $1}'`;
 ls -l /dev/disk/by-path/ | grep "$host" &>/dev/null;
 if [ $? -eq 0 ]; then
  disks=(`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk '{print $9}'`);
  for devdisk in "${disks[@]}"; do
   devdisk=`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk -F'->' '{print $2}'`;
 
   devformatted=`echo $devdisk | awk -F's' '{print $2}'`;
   newdiskid=`ls -l /dev/disk/by-id/ | grep "$devdisk" | grep -v part | grep scsi | awk -F'scsi-' '{print $2}' | awk -F' ->' '{print $1}'`;
   echo newdiskid=$newdiskid
   /sbin/zpool list -vH | grep $newdiskid &>/dev/null
   if [ $? -ne 0 ]; then 
    idledisk=("${idledisk[@]}" "$host,$newdiskid");
   fi
  done
 fi
done < $iscsimapping
echo idledisks=${idledisk[@]};
if [ "${#idledisk[@]}" -gt 2 ]; then
 nextpool=`zpool list  | wc -l`
 x=$((${#idledisk[@]}-1));
 y=$((x-1));  
 disk1=`echo ${idledisk[$x]} | awk -F',' '{print $2}'`
 disk2=`echo ${idledisk[$y]} | awk -F',' '{print $2}'`
# dd if=/dev/zero of=/dev/disk/by-id/scsi-"$newdisk" bs=512 count=1 ;
#  sleep 2
  /sbin/zpool labelclear /dev/disk/by-id/scsi-${disk1};
  /sbin/zpool labelclear /dev/disk/by-id/scsi-${disk2};
  sleep 2
#  parted /dev/disk/by-id/scsi-"$newdisk" mklabel msdos;
 /sbin/zpool create -f p${nextpool} mirror scsi-${disk1} scsi-${disk2} ;
 echo /sbin/zpool create p${nextpool} mirror /dev/disk/by-id/scsi-${disk1} /dev/disk/by-id/scsi-${disk2} ;
 if [ $? -eq 0 ]; then 
#   host=`echo ${idledisk[$i]} | awk -F',' '{print $1}'`
#   devdisk=`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk -F'->' '{print $2}'`;
#   devformatted=`echo $devdisk | awk -F's' '{print $2}'`;
#   sed -i "/$host/d"  ${iscsimapping}new ; 
#   echo $host "s"$devformatted $newdisk >> ${iscsimapping}new;
  unset idledisk[$x];
  unset idledisk[$y];
 fi
fi 
