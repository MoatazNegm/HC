cd /pace
iscsimapping='/pacedata/iscsimapping';
myhost=`hostname`
runningpools='/pacedata/pools/runningpools';
declare -a idledisk=();
declare -a hostdisk=();
declare -a runninghosts=(`cat $iscsimapping | grep -v notconnected | awk '{print $1}'`);
phost='';
for host in "${runninghosts[@]}" ; do
 echo $phost | grep $host
 if [ $? -ne 0 ]; then
  phost=${phost}' '${host};
  hostp=`ssh $host /sbin/zpool list -Hv ` 
  hostps=${hostps}' '${hostp};
 fi
done
echo $hostps >> $runningpools
sleep 2
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
 if [ ${#idledisk[@]} -eq 0 ]; then
   disk2=`echo ${localdisk} | awk -F',' '{print $2}'`
   /sbin/zpool labelclear /dev/disk/by-id/${disk2};
   rm -rf /p${nextpool} &>/dev/null
   /sbin/zpool create -f p${nextpool} ${disk2} ;
   echo /sbin/zpool create p${nextpool} /dev/disk/by-id/scsi-${disk2} ;
 else
  x=$((${#idledisk[@]}-1));
  if [ $x -ge 0 ]; then
   disk1=`echo ${idledisk[$x]} | awk -F',' '{print $2}'`
   disk2=`echo ${localdisk} | awk -F',' '{print $2}'`
   /sbin/zpool labelclear /dev/disk/by-id/${disk1};
   /sbin/zpool labelclear /dev/disk/by-id/${disk2};
   rm -rf /p${nextpool} &>/dev/null
   /sbin/zpool create -f p${nextpool} mirror ${disk1} ${disk2} ;
   echo /sbin/zpool create p${nextpool} mirror /dev/disk/by-id/scsi-${disk1} /dev/disk/by-id/scsi-${disk2} ;
   if [ $? -eq 0 ]; then 
    unset idledisk[$x];
   fi
  fi
 fi
done
