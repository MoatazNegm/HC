cd /pace
export ETCDCTL_API=3
perfmon=`cat /pacedata/perfmon`
myhost=`hostname -s`
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
/TopStor/queuethis.sh Iscsirefresh start system &
fi
declare -a iscsitargets=(`ETCDCTL_API=3 ./iscsiclients.py | grep target | awk -F'/' '{print $2}'`);
echo iscsitargets=$iscsitargets
systemctl status iscsid &>/dev/null
if [ $? -ne 0 ];
then
 systemctl start iscsid 
fi
systemctl status target &>/dev/null
if [ $? -ne 0 ];
then
 systemctl start target
fi
systemctl status iscsi &>/dev/null
if [ $? -ne 0 ];
then
 systemctl start iscsi 
fi

echo /sbin/iscsiadm -m session --rescan
/sbin/iscsiadm -m session --rescan &>/dev/null
if [ $? -ne 0 ];
then
 ff=`ls /var/lib/iscsi/nodes/* | awk '{print $NF}' | grep $myhost` 
 echo ff=$ff
 rm -rf /var/lib/iscsi/nodes/$ff 
fi
needrescan=0;
sessions=`/sbin/iscsiadm -m session`
for hostline in "${iscsitargets[@]}"
do
 echo $sessions | grep $hostline
 if [ $? -ne 0 ];
 then
  echo '#####################################'
  echo $sessions
  echo hostline=$hostline
  echo $myhost | grep $hostline
  host=` ETCDCTL_API=3 ./etcdget.py ActivePartners/$hostline`
  echo hihi
  ping -c 1 -W 1 $host &>/dev/null
  if [ $? -eq 0 ]; then
   needrescan=1;
   echo firsthost=$host
   echo /sbin/iscsiadm -m discovery --portal $host --type sendtargets -o delete -o new 
   hostiqn=`/sbin/iscsiadm -m discovery --portal $host --type sendtargets 2>/root/iscsirefresh | awk '{print $2}'`
   echo hostiqn=$hostiqn
   #echo /sbin/iscsiadm --mode node --targetname $hostiqn --portal $host:3260 -u 2>/dev/null
   echo /sbin/iscsiadm --mode node --targetname $hostiqn --portal $host:3260 --login
   /sbin/iscsiadm --mode node --targetname $hostiqn --portal $host --login
  fi
 fi
done
 echo $perfmon | grep 1
 if [ $? -eq 0 ]; then
/TopStor/queuethis.sh Iscsirefresh stop system &
fi
