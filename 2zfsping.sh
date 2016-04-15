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
for pool in "${pools[@]}"; do
 /sbin/zpool clear p1 &>/dev/null
 /sbin/zpool status $pool | grep "was /dev" &>/dev/null
 if [ $? -eq 0 ]; then
  faildisk=`/sbin/zpool status $pool | grep "was /dev" | awk -F'-id/' '{print $2}' | awk -F'-part' '{print $1}'`;
  /sbin/zpool detach $pool $faildisk &>/dev/null;
 fi 
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


while read -r  hostline ; do
 echo $hostline | grep notconnected >/dev/null
 if [ $? -ne 0 ]; then 
  host=`echo $hostline | awk '{print $1}'`
  ping -c 1 -W 1 $host &>/dev/null; 
  if [ $? -ne 0 ]; then
    hostdiskid=`echo $hostline | awk '{print $3}'`
    for pool in "${pools[@]}"; do
     /sbin/zpool list -Hv $pool | grep "$hostdiskid" &>/dev/null
     if [ $? -eq 0 ]; then 
      /sbin/zpool offline $pool scsi-"$hostdiskid" ;
      if [ $? -eq 0 ]; then 
    	sed -i "/$host/d"  ${iscsimapping}new ; 
   	echo $host notconnected >> ${iscsimapping}new;
      fi
     fi
    done;
  fi
 else
  host=`echo $hostline | awk '{print $1}'`
  ping -c 1 -W 1 $host &>/dev/null
  if [ $? -eq 0 ]; then
   hostiqn=`/sbin/iscsiadm -m discovery --portal $host --type sendtargets | awk '{print $2}'`
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -u &>/dev/null
   /sbin/iscsiadm -m node --targetname $hostiqn --portal $host -l &>/dev/null
   sed -i "/$host/d"  ${iscsimapping}new ; 
   echo $host "s"$devformatted $newdiskid >> ${iscsimapping}new;
   sleep 1;
  fi
 fi
 ls -l /dev/disk/by-path/ | grep "$host" &>/dev/null;
 if [ $? -eq 0 ]; then
  devdisk=`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk -F'->' '{print $2}'`;
  devformatted=`echo $devdisk | awk -F's' '{print $2}'`;
  newdiskid=`ls -l /dev/disk/by-id/ | grep "$devdisk" | grep -v part | grep scsi | awk -F'scsi-' '{print $2}' | awk -F' ->' '{print $1}'`;
  idledisk=("${idledisk[@]}" "$host,$newdiskid");
 fi
done < $iscsimapping
for pool in "${pools[@]}"; do
 singledisk=`/sbin/zpool list -Hv $pool | wc -l`
 if [ $singledisk -le 2 ]; then
  runningdisk=`/sbin/zpool list -Hv | grep scsi | awk '{print $1}'`;
  dd if=/dev/zero of=/dev/disk/by-id/scsi-"$newdiskid" bs=512 count=1 &>/dev/null;
  /sbin/zpool clear $pool &>/dev/null
  sleep 1;
  i=$((${#idledisk[@]}-1));
  newdisk=`echo ${idledisk[$i]} | awk -F',' '{print $2}'`
  /sbin/zpool attach $pool $runningdisk scsi-"$newdisk" &>/dev/null;
  if [ $? -eq 0 ]; then 
   host=`echo ${idledisk[$i]} | awk -F',' '{print $1}'`
   devdisk=`ls -l /dev/disk/by-path/ | grep "$host" |  grep -v part | awk -F'->' '{print $2}'`;
   devformatted=`echo $devdisk | awk -F's' '{print $2}'`;
   sed -i "/$host/d"  ${iscsimapping}new ; 
   echo $host "s"$devformatted $newdisk >> ${iscsimapping}new;
   unset idledisk[$i];
  fi
 fi 
done
cp ${iscsimapping}new $iscsimapping
sleep 2;
