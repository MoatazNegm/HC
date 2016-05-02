cd /pace
iscsimapping='/pacedata/iscsimapping';
myhost=`hostname`
exporpool=`/sbin/zpool import`
declare -a pools=(`/sbin/zpool list -H | awk '{print $1}'`)
runningpools='/pacedata/pools/runningpools';
/sbin/zpool list -Hv  > $runningpools
declare -a idledisk=();
declare -a hostdisk=();
while read -r hostline; do
 echo $hostline | grep notconnected  &>/dev/null;
 if [ $? -ne 0 ]; then
  host=`echo $hostline | awk '{print $1}'`;
  ssh $host /sbin/zpool list -Hv | ( cat >> $runningpools);
 fi
done < $iscsimapping
while read -r  hostline ; do
 host=`echo $hostline | awk '{print $1}'`;
 ls -l /dev/disk/by-path/ | grep "$host" &>/dev/null;
 if [ $? -eq 0 ]; then
  devformatted=`echo $hostline | awk '{print $2}'`;
  newdiskid=`echo $hostline | awk '{print $3}'`;
  echo newdiskid=$newdiskid
  cat $runningpools | grep "$newdiskid" &>/dev/null
  if [ $? -ne 0 ]; then 
   echo $host | grep $myhost &>/dev/null
   if [ $? -eq 0 ]; then
    hostdisk=("${hostdisk[@]}" "$host,$newdiskid");
   else
    idledisk=("${idledisk[@]}" "$host,$newdiskid");
   fi
  fi
 fi
done < $iscsimapping
for localdisk in "${hostdisk[@]}"; do
 nextpool=`zpool list  | wc -l`
 echo idledisk=${#idledisk[@]} localdisk=$localdisk 
 x=$((${#idledisk[@]}-1));
 if [ $x -ge 0 ]; then
  disk1=`echo ${idledisk[$x]} | awk -F',' '{print $2}'`
  disk2=`echo ${localdisk} | awk -F',' '{print $2}'`
  /sbin/zpool labelclear /dev/disk/by-id/${disk1};
  /sbin/zpool labelclear /dev/disk/by-id/${disk2};
  /sbin/zpool create -f p${nextpool} mirror ${disk1} ${disk2} ;
  echo /sbin/zpool create p${nextpool} mirror /dev/disk/by-id/scsi-${disk1} /dev/disk/by-id/scsi-${disk2} ;
  if [ $? -eq 0 ]; then 
   unset idledisk[$x];
  fi
 fi
done
