cd /pace
iscsimapping='/pace/iscsimapping';
cp ${iscsimapping} ${iscsimapping}new;
declare -a pools=(`/sbin/zpool list -H | awk '{print $1}'`)
runninghosts=`cat $iscsimapping | grep -v notconnected`
newrunninghosts=`cat $iscsimapping | grep -v notconnected`
declare -a deadhosts=(`cat $iscsimapping | grep  notconnected`)
newdeadhosts=`cat $iscsimapping | grep  notconnected`
dirty=0;
while read -r  hostline ; do
 echo $hostline | grep notconnected
 if [ $? -ne 0 ]; then 
  host=`echo $hostline | awk '{print $1}'`
  echo host=$host
  ping -c 1 -W 1 $host; 
  if [ $? -ne 0 ]; then
    echo problem;
    hostdiskid=`echo $hostline | awk '{print $3}'`
    for pool in "${pools[@]}"; do
     /sbin/zpool list -Hv $pool | grep "$hostdiskid" 
     if [ $? -eq 0 ]; then 
      /sbin/zpool offline $pool scsi-"$hostdiskid" ;
      if [ $? -eq 0 ]; then 
    	sed -i "/$host/d"  ${iscsimapping}new ; 
   	echo $host notconnected >> ${iscsimapping}new;
        dirty=1;
      fi
     fi
    done;
  fi
 else
  echo for notconnected
  host=`echo $hostline | awk '{print $1}'`
  ping -c 1 -W 1 $host
  if [ $? -eq 0 ]; then
   echo fixing
   hostiqn=`/sbin/iscsiadm -m discovery --portal $host --type sendtargets | awk '{print $2}'`
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -u
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -l
   sleep 2;
   echo host=$host
   devdisk=`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk -F'->' '{print $2}'`;
   devformatted=`echo $devdisk | awk -F's' '{print $2}'`;
   newdiskid=`ls -l /dev/disk/by-id/ | grep "$devdisk" | grep -v part | grep scsi | awk -F'scsi-' '{print $2}' | awk -F' ->' '{print $1}'`;
   offlinedisk=(`/sbin/zpool status | grep  OFFLINE | awk '{print $1}'`)
   replacedisk="${offlinedisk[0]}"
   echo newdisk=$newdiskid
   for pool in "${pools[@]}"; do
    /sbin/zpool list -Hv $pool | grep "$hostdiskid" 
    if [ $? -eq 0 ]; then 
     /sbin/zpool detach  $pool $replacedisk;
     runningdisk=`/sbin/zpool list -Hv $pool | grep scsi | awk '{print $1}'`;
     dd if=/dev/zero of=/dev/disk/by-id/scsi-"$newdiskid" bs=512 count=1;
     sleep 1;
     /sbin/zpool attach $pool $runningdisk scsi-"$newdiskid" ;
     if [ $? -eq 0 ]; then 
      sed -i "/$host/d"  ${iscsimapping}new ; 
      echo $host "s"$devformatted $newdiskid >> ${iscsimapping}new;
      dirty=1;
     fi
    fi
   done;
  fi 
 fi
done < <(cat $iscsimapping)
echo done;
if [ $dirty -eq 1 ]; then 
 cp ${iscsimapping}new $iscsimapping
fi
