cd /pace 
iscsimapping='/pacedata/iscsimapping'
declare -a pools=();
/sbin/zpool export -a
sh iscsienable.sh
sh addtargetdisks.sh
sh iscsirefresh.sh
sleep 2;
sh listingtargets.sh 
runninghosts=`cat $iscsimapping | grep -v notconnected | wc -l`
if [ $runninghosts -le 1 ]; then
 pools=(`/sbin/zpool import | grep "pool:" | awk '{print $2}'`);
 for pool in "${pools[@]}"; do
  ls /pacedata/pools/ | grep $pool &>/dev/null
  if [ $? -eq 0 ]; then
   /sbin/zpool import -c '/pacedata/pools/'${pool}.cache $pool;
   /sbin/zpool clean $pool;
  fi
 done
fi
