cd /pace 
iscsimapping='/pacedata/iscsimapping'
declare -a pools=();
/sbin/zpool export -a
sh iscsienable.sh
sh addtargetdisks.sh &>/dev/null
sh iscsirefresh.sh &>/dev/null
sleep 2;
sh listingtargets.sh 
runninghosts=`cat $iscsimapping | grep -v notconnected | wc -l`
if [ $runninghosts -le 1 ]; then
 echo searching pools
 pools=(`/sbin/zpool import | grep "pool:" | awk '{print $2}'`);
 if [ ${#pools[@]} -gt 0 ]; then
  echo found pools ${pools[@]}
  for pool in "${pools[@]}"; do
    echo importing $pool
   ls /pacedata/pools/ | grep $pool &>/dev/null
   if [ $? -eq 0 ]; then
    echo start import
    /sbin/zpool import -c '/pacedata/pools/'${pool}.cache $pool;
   else
    echo as it is $pool
    /sbin/zpool import $pool;
   fi
   /sbin/zpool clear $pool;
  done
 fi
fi
