cd /pace
iscsimapping='/pace/iscsimapping';
myhost=`hostname`
exporpool=`/sbin/zpool import`
declare -a pools=(`/sbin/zpool list -H | awk '{print $1}'`)
declare -a idledisk=("hi,world");
declare -a hostdisk=("hi,world");

while read -r  hostline ; do
 host=`echo $hostline | awk '{print $1}'`;
 ls -l /dev/disk/by-path/ | grep "$host" &>/dev/null;
 if [ $? -eq 0 ]; then
  disks=(`ls -l /dev/disk/by-path/ | grep "$host" | grep -v wwn | grep -v part | awk '{print $11}'`);
  for devdisk in "${disks[@]}"; do
   devformatted='/dev/'`echo $devdisk | awk -F'/' '{print $3}'`;
   newdiskid=`ls -l /dev/disk/by-id/ | grep "$devdisk" | grep -v part | grep -v wwn | awk '{print $9}'`;
   echo newdiskid=$newdiskid
   /sbin/zpool list -vH | grep "$newdiskid" &>/dev/null
   if [ $? -ne 0 ]; then 
    echo $exporpool | grep "$newdiskid" &>/dev/null
    if [ $? -ne 0 ]; then
     echo $host | grep $myhost &>/dev/null
     if [$? -eq 0 ]; then
      hostdisk=("${hostdisk[@]}" "$host,$newdiskid");
     else
      idledisk=("${idledisk[@]}" "$host,$newdiskid");
     fi
    fi
   fi
  done
 fi
done < $iscsimapping
for localdisk in "${hostdisk[@]}"; do
 nextpool=`zpool list  | wc -l`
 x=$((${#idledisk[@]}-1));
 disk1=`echo ${idledisk[$x]} | awk -F',' '{print $2}'`
 disk2=`echo ${localdisk} | awk -F',' '{print $2}'`
 /sbin/zpool labelclear /dev/disk/by-id/${disk1};
 /sbin/zpool labelclear /dev/disk/by-id/${disk2};
 /sbin/zpool create -f p${nextpool} mirror ${disk1} ${disk2} ;
 echo /sbin/zpool create p${nextpool} mirror /dev/disk/by-id/scsi-${disk1} /dev/disk/by-id/scsi-${disk2} ;
 if [ $? -eq 0 ]; then 
  unset idledisk[$x];
 fi
done
