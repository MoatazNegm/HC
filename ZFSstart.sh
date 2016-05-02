cd /pace 
iscsimapping='/pacedata/iscsimapping'
runningpools='/pacedata/pools/runningpools';
/sbin/zpool list -H > $runningpools
declare -a pools=();
/sbin/zpool export -a
#sh iscsienable.sh
#sh addtargetdisks.sh 
sh iscsirefresh.sh 
sleep 1;
sh listingtargets.sh 
sleep 1;
cat $iscsimapping | grep notconnected &>/dev/null
if [ $? -eq 0 ]; then
 echo searching pools
 pools=(`/sbin/zpool import | grep "pool:" | awk '{print $2}'`);
 if [ ${#pools[@]} -gt 0 ]; then
  echo found pools ${pools[@]}
  while read -r hostline; do
   echo $hostline | grep notconnected &>/dev/null
   if [ $? -ne 0 ]; then
    host=`echo $hostline | awk '{print $1}'`;
     ssh $host /sbin/zpool list -H | (cat >> $runningpools);
   fi
  done < $iscsimapping
  for pool in "${pools[@]}"; do
    echo importing $pool
   cat $runningpools | grep $pool &>/dev/null
   if [ $? -ne 0 ]; then 
    ls /pacedata/pools/ | grep $pool &>/dev/null
    if [ $? -eq 0 ]; then
     echo start import
     /sbin/zpool import -c '/pacedata/pools/'${pool}.cache $pool &>/dev/null;
     /sbin/zpool import $pool &>/dev/null;
     /sbin/zpool clear $pool;
    else
     echo as it is $pool
     /sbin/zpool import $pool &>/dev/null;
    fi
    /sbin/zpool clear $pool;
   fi
  done
 fi
fi
