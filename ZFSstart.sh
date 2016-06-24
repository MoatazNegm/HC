cd /pace 
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
iscsimapping='/pacedata/iscsimapping'
runningpools='/pacedata/pools/runningpools';
myhost=`hostname`
echo runningpools > ${runningpools}
/sbin/zpool list -H > ${runningpools}$myhost
while read -r runpool; do
 echo $myhost $runpool >> $runningpools
done < ${runningpools}$myhost
rm -rf ${runningpools}$myhost &>/dev/null
declare -a pools=();
/sbin/zpool export -a
#sh iscsienable.sh
/pace/addtargetdisks.sh 
/pace/iscsienable.sh
/pace/iscsirefresh.sh 
sleep 1;
sh listingtargets.sh
ohosts=`cat $iscsimapping | grep -v notconnected | wc -l `
if [ $ohosts -eq 1 ]; then
 /sbin/zpool import -a
fi
#sh init
#sh initdisks.sh
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
     ssh $host /sbin/zpool list -H | (cat >> ${runningpools}$host)
     while read -r runpool; do
      echo $host $runpool >> $runningpools
     done < ${runningpools}$host
      rm -rf ${runningpools}$host &>/dev/null
   fi
  done < $iscsimapping
  for pool in "${pools[@]}"; do
    echo importing $pool
   echo cat $runningpools  grep -v $myhost  grep $pool
   cat $runningpools | grep -v $myhost | grep $pool &>/dev/null
   if [ $? -ne 0 ]; then 
    ls /pacedata/pools/ | grep $pool &>/dev/null
    if [ $? -eq 0 ]; then
     echo start import
     if [ -d /$pool ]; then rm -rf /$pool; fi
     /sbin/zpool import -c '/pacedata/pools/'${pool}.cache $pool &>/dev/null;
     echo /sbin/zpool import -c '/pacedata/pools/'${pool}.cache $pool; 
     /sbin/zpool import $pool &>/dev/null;
     /sbin/zpool clear $pool;
    else
     echo as it is $pool
     if [ -d /$pool ]; then rm -rf /$pool; fi
     /sbin/zpool import $pool &>/dev/null;
    fi
    /sbin/zpool clear $pool;
   fi
  done
 fi
fi
