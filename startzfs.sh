#!/bin/sh
cd /pace
export ETCDCTL_API=3
echo >/etc/exports
/sbin/pcs resource disable namespaces  2>/dev/null
/sbin/pcs resource disable  ip-all  2>/dev/null
/sbin/pcs resource disable  dataip  2>/dev/null
/sbin/zpool export -a 2>/dev/null
#yes | cp /TopStor/smb.conf /etc/samba/
#yes | cp /TopStor/exports /etc/
ln -f /etc/passwd  /opt/passwds/passwd
ln -f /etc/group  /opt/passwds/group
ln -f /etc/shadow  /opt/passwds/shadow
echo starting startzfs > /root/tmp2
#systemctl start smb &
iscsimapping='/pacedata/iscsimapping';
runningpools='/pacedata/pools/runningpools';
enpdev='enp0s8'
myhost=`hostname -s`
#/sbin/rabbitmqctl add_user rabbmezo HIHIHI 2>/dev/null
#/sbin/rabbitmqctl set_permissions -p / rabbmezo ".*" ".*" ".*" 2>/dev/null
#/sbin/rabbitmqctl set_user_tags rabbmezo administrator
myip=`/sbin/pcs resource show CC | grep Attributes | awk -F'ip=' '{print $2}' | awk '{print $1}'`
ccnic=`/sbin/pcs resource show CC | grep nic\= | awk -F'nic=' '{print $2}' | awk '{print $1}'`
/sbin/pcs resource delete --force namespaces  2>/dev/null
/sbin/pcs resource delete --force ip-all  2>/dev/null
/sbin/pcs resource delete --force dataip  2>/dev/null
echo starting etcd as local >>/root/tmp2
./etccluster.py 'local' $myip 2>/dev/null
chmod +r /etc/etcd/etcd.conf.yml 2>/dev/null
systemctl daemon-reload 2>/dev/null
systemctl stop etcd 2>/dev/null
systemctl start etcd 2>/dev/null
datenow=`date +%m/%d/%Y`; timenow=`date +%T`;
knownsearch=0
result='nohost'
./etcdputlocal.py $myip ActivePartners/$myhost $myip
toreset=`./etcdgetlocal.py $myip toreset`'r'
echo $toreset | grep yes
if [ $? -eq 0 ];
then
 ./etcddellocal.py $myip "" --prefix
 ./etcdputlocal.py $myip configured yes
 targetcli clearconfig confirm=true
 /TopStor/logmsg2.sh $datenow $timenow $myhost Evacuaesu01 info system $myhost
else
 result=` ETCDCTL_API=3 ./clustersearch.py $myip 2>/dev/null | grep hostis | awk -F'=' '{print $2}'`
fi
echo $result | grep nohost 
if [ $? -ne 0 ];
then
 echo found cluster with leader $result.. no need for node search >>/root/tmp2
 knownsearch=1
else
 configured=`ETCDCTL_API=3 ./etcdgetlocal.py $myip configured` 
 echo configured is $configured >>/root/tmp2
 systemctl stop etcd & 
 echo $configured | grep yes 
 if [ $? -eq 0 ];
 then
  result='nothing'
 else
  echo starting nodesearch>>/root/tmp2
  result=` ETCDCTL_API=3 ./nodesearch.py $myip 2>/dev/null`
  echo finish nodesearch with ip=$myip, result=$result >>/root/tmp2
 fi
fi
freshcluster=0
echo $result > /root/hihi
echo myip=$myip >> /root/hihi
echo $result | grep nothing 
if [ $? -eq 0 ];
then
 echo no node is found so making me as primary>>/root/tmp2
 rm -rf /pacedata/running*
 freshcluster=1
  ./etccluster.py 'new' $myip 2>/dev/null
 chmod +r /etc/etcd/etcd.conf.yml 2>/dev/null
 echo startinetcd >>/root/tmp2
 systemctl daemon-reload 2>/dev/null
 systemctl start etcd 2>/dev/null
 while true;
 do
  echo starting etcd=$?
  systemctl status etcd
  if [ $? -eq 0 ];
  then
   break
  else
   sleep 1
  fi
 done
 echo started etcd as primary>>/root/tmp2
 datenow=`date +%m/%d/%Y`; timenow=`date +%T`;
 ./runningetcdnodes.py $myip 2>/dev/null
 /TopStor/HostManualconfigTZlocal $myip 
 /TopStor/HostManualconfigNTPlocal $myip
 cd /pace
 ./etcdget.py configured | grep 1
 if [ $? -eq 0 ];
 then
  ./etcdput.py configured no
 else 
  ./etcdget.py frstnode | grep dhcp
  if [ $? -ne 0 ];
  then
   ./etcdput.py frstnode $myhost
  fi
 fi
 gateway=`ETCDCTL_API=3 /TopStor/etcdget.py gw`
 echo $gateway | grep '\.'
 if [ $? -eq 0 ];
 then
  route del default
  route add default gw $gateway
 fi 
 tzone=`ETCDCTL_API=3 /TopStor/etcdget.py tz`
 echo $tzone | grep '\/'
 if [ $? -ne 0 ];
 then
  tzone='@@'`timedatectl | grep  zone | awk -F':' '{print $2}'` 
  tzone=${tzone//,/@}
  tzone=${tzone// /_}
#  ./etcdput.py tz $tzone
 fi
 ntp=`ETCDCTL_API=3 /TopStor/etcdget.py ntp`
 echo ntp=$ntp >/root/ntptemp
 rm -rf /etc/chrony.conf
 cp /TopStor/chrony.conf /etc/
 echo $ntp | grep '\.'
 if [ $? -eq 0 ];
 then
  sed -i "s/MASTERSERVER/$ntp/g" /etc/chrony.conf
 else
  sed -i '/MASTERSERVER/,+1 d' /etc/chrony.conf
  ntp=`cat /etc/chrony.conf | grep server | grep -v servers | head -1 | awk '{print $2}'`
  ./etcdgput.py ntp $ntp
 fi
 systemctl restart chronyd
 /TopStor/logmsg2.sh $datenow $timenow $myhost Partst03 info system $myhost $myip
 ./etcddel.py known --prefix 2>/dev/null 
 ./etcddel.py possbile --prefix 2>/dev/null 
 ./etcddel.py ready --prefix 2>/dev/null 
 ./etcddel.py locked --prefix 2>/dev/null 
 ./etcddel.py cannot --prefix 2>/dev/null 
 ./etcddel.py request --prefix 2>/dev/null 
 allow=`ETCDCTL_API=3 ./etcdget.py allowedPartners ` 2>/dev/null 
 echo checking allow=$allow >>/root/tmp2
 echo $allow | grep 1
 if [ $? -eq 0 ];
 then
  ./etcdput.py allowedPartners notallowed 
  echo started setting allowedPartners to allow >>/root/tmp2
 fi 
 myalias=`ETCDCTL_API=3 /pace/etcdget.py alias/$myhost`
 if [[ $myalias -eq -1 ]];
 then
   /pace/etcdput.py alias/$myhost $myhost
 fi
 rm -rf /var/lib/iscsi/nodes/* 2>/dev/null
 echo creating namespaces >>/root/tmp2
 ./setnamespace.py $enpdev
 ./setdataip.py
 echo created namespaces >>/root/tmp2
 ./etcddel.py leader --prefix 2>/dev/null
 ./etcddel.py pools --prefix 2>/dev/null
 ./etcddel.py poolsnxt --prefix 2>/dev/null
 ./etcddel.py cann --prefix 2>/dev/null
 ./etcddel.py prop --prefix 2>/dev/null
 ./etcddel.py Snapperiod --prefix 2>/dev/null
 ./etcdput.py leader/$myhost $myip 2>/dev/null
 ./etcdput.py primary/name $myhost 2>/dev/null
 ./etcdput.py primary/address $myip 2>/dev/null
 ./etcddel.py known --prefix 2>/dev/null
 ./etcddel.py possible --prefix 2>/dev/null
 ./etcddel.py localrun --prefix 2>/dev/null
 ./etcddel.py to  --prefix 2>/dev/null
 ./etcddel.py hosts  --prefix 2>/dev/null
 ./etcddel.py oldhosts  --prefix 2>/dev/null
 ./etcddel.py vol  --prefix 2>/dev/null
 ./etcddel.py ipaddr  --prefix 2>/dev/null
 ./etcddel.py active --prefix 2>/dev/null
 systemctl start iscsid &
 systemctl start iscsi &
 systemctl start topstorremote
 systemctl start topstorremoteack
 systemctl start servicewatchdog 
 cat /etc/passwd | grep NoUser 
 if [ $? -ne 0 ];
 then
  /TopStor/UnixAddUser NoUser NoHome groupsnull 1234567890YosuefNadody NoHome 1G admin
 fi
 cat /etc/passwd | grep Everyone
 if [ $? -ne 0 ];
 then
  /TopStor/UnixAddGroup Everyone usersNoUser admin
 fi
 /sbin/zpool export -a 2>/dev/null
 rm -rf /pdhcp*
 /TopStor/crontoetc.py all &
 echo startiscsiwatchdog >>/root/tmp2
 /pace/iscsiwatchdog.sh 2>/dev/null
 echo finished iscsiwatchdog >>/root/tmp2

 echo deleted knowns and added leader >>/root/tmp2
else
 echo found other host as primary.. checking if it shares same host name>>/root/tmp2
 cat /pacedata/runningetcdnodes.txt | grep $myhost &>/dev/null
 if [ $? -ne 0 ];
 then
  leaderall=` ./etcdget.py leader --prefix `
  leader=`echo $leaderall | awk -F'/' '{print $2}' | awk -F"'" '{print $1}'`
  leaderip=`echo $leaderall | awk -F"')" '{print $1}' | awk -F", '" '{print $2}'`
   /TopStor/logmsg.py Partst04 info system $myhost $myip
  ./clearnamespace.py $enpdev
  ./cleardataip.py $enpdev
  if [ $knownsearch -eq 0 ];
  then
   echo starting etcd as local >>/root/tmp2
    ./etccluster.py 'local' $myip 2>/dev/null
   chmod +r /etc/etcd/etcd.conf.yml 2>/dev/null
   rm -rf /var/lib/etcd/*
   systemctl daemon-reload 2>/dev/null
   systemctl stop etcd 2>/dev/null
   systemctl start etcd 2>/dev/null
   while true;
   do
    echo starting etcd=$?
    systemctl status etcd
    if [ $? -eq 0 ];
    then
     break
    else
     sleep 1
    fi
   done
  fi
  ./etcdputlocal.py $myip 'local/'$myhost $myip
  echo sync leader with local database >>/root/tmp2
  rm -rf /etc/chrony.conf
  cp /TopStor/chrony.conf /etc/
  /TopStor/HostManualconfigTZ 
  /TopStor/HostManualconfigNTP
  cd /pace
  systemctl restart chronyd
  leaderip=` ./etcdget.py leader/$leader `
  sed -i "s/MASTERSERVER/$leaderip/g" /etc/chrony.conf
  ./etcdsync.py $myip primary primary 2>/dev/null
  ./etcddellocal.py $myip known --prefix 2>/dev/null
  ./etcddellocal.py $myip activepool --prefix 2>/dev/null
  ./etcddellocal.py $myip ipaddr --prefix 2>/dev/null
  ./etcddellocal.py $myip localrun --prefix 2>/dev/null
  ./etcddellocal.py $myip run --prefix 2>/dev/null
  ./etcddellocal.py $myip pools --prefix 2>/dev/null
  ./etcddellocal.py $myip prop --prefix 2>/dev/null
  ./etcddellocal.py $myip poolsnxt --prefix 2>/dev/null
  ./etcddellocal.py $myip vol --prefix 2>/dev/null
  ./etcdsync.py $myip known known 2>/dev/null
  ./etcdsync.py $myip allowedPartners allowedPartners 2>/dev/null
  ./etcdsync.py $myip activepool activepool 2>/dev/null
  ./etcdsync.py $myip ipaddr ipaddr 2>/dev/null
  ./etcdsync.py $myip pools pools 2>/dev/null
  ./etcdsync.py $myip poolsnxt poolsnxt 2>/dev/null
  ./etcdsync.py $myip namespace namespace 2>/dev/null
  ./etcdsync.py $myip volumes volumes 2>/dev/null
  ./etcdsync.py $myip dataip dataip 2>/dev/null
  ./etcdsync.py $myip localrun localrun 2>/dev/null
  ./etcdsync.py $myip leader known 2>/dev/null
  ./etcdsync.py $myip logged logged 2>/dev/null
  ./etcdsync.py $myip updlogged updlogged 2>/dev/null
  ./etcdsync.py $myip ActivePartners ActivePartners 2>/dev/null
  ./etcdsync.py $myip ntp ntp 2>/dev/null
  ./etcdsync.py $myip tz tz 2>/dev/null
  ./etcdsync.py $myip gw gw 2>/dev/null
  /TopStor/etcdsyncnext.py $myip nextlead nextlead 2>/dev/null
  /bin/crontab /TopStor/plaincron
  ./etcdsync.py $myip Snapperiod Snapperiod 2>/dev/null
  /TopStor/etctocron.py
  ./etcddel.py known/$myhost --prefix 2>/dev/null
  ./etcddel.py oldhosts/$myhost  --prefix 2>/dev/null
  ./etcddel.py hosts/$myhost  --prefix 2>/dev/null
  /sbin/rabbitmqctl add_user rabb_$leader YousefNadody 2>/dev/null
  /sbin/rabbitmqctl set_permissions -p / rabb_$leader ".*" ".*" ".*" 2>/dev/null
  ./etcddellocal.py $myip users --prefix 2>/dev/null
  ./usersyncall.py $myip
  ./groupsyncall.py $myip
  gateway=`ETCDCTL_API=3 /TopStor/etcdget.py gw`
  echo $gateway | grep '\.'
  if [ $? -eq 0 ];
  then
   route del default
   route add default gw $gateway
  fi 
  cd /pace/
  myalias=`ETCDCTL_API=3 /pace/etcdgetlocal.py $myip alias/$myhost`
  if [[ $myalias -ne -1 ]];
  then
   /pace/etcdput.py alias/$myhost $myalias
  else
   myalias=`ETCDCTL_API=3 /pace/etcdget.py alias/$myhost`
   if [[ $myalias -eq -1 ]];
   then
    ./etcdput.py alias/$myhost $myhost
   fi
  fi
  ./etcddellocal.py $myip alias --prefix 2>/dev/null
  ./etcdsync.py $myip alias alias 2>/dev/null
  systemctl start iscsid &
  systemctl start iscsi &
  systemctl start topstorremote
  systemctl start topstorremoteack
  systemctl start servicewatchdog 
  echo etcd started as local >>/root/tmp2
  rm -rf /var/lib/iscsi/nodes/* 2>/dev/null
  echo starting iscsiwaatchdog >>/root/tmp2
  /sbin/zpool export -a
  /pace/iscsiwatchdog.sh $myip $myhost $leader 2>/dev/null
  echo started iscsiwaatchdog >>/root/tmp2
 fi
fi
/TopStor/HostgetIPs &

echo starting disk LIO check >>/root/tmp2
myhost=`hostname -s`
hostnam=`cat /TopStordata/hostname`
poollist='/pacedata/pools/'${myhost}'poollist';
lastreboot=`uptime -s`
seclastreboot=`date --date="$lastreboot" +%s`
secrunning=`cat $runningpools | grep runningpools | awk '{print $2}'`
if [ -z $secrunning ]; then
 echo hithere: $lastreboot : $seclastreboot
 secdiff=222;
else
 secdiff=$((seclastreboot-secrunning));
fi
if [ $secdiff -ne 0 ]; then
 echo runningpools $seclastreboot > $runningpools
echo starting keysend >>/root/tmp2
 ./keysend.sh $myip &>/dev/null
# pcs resource create IPinit ocf:heartbeat:IPaddr2 nic="$ccnic" ip="10.11.11.254" cidr_netmask=24 op monitor on-fail=restart 2>/dev/null
# pcs resource debug-start IPinit 2>/dev/null
 rm -rf /TopStor/key/adminfixed.gpg && cp /TopStor/factory/factoryadmin /TopStor/key/adminfixed.gpg
echo i all zpool exported >>/root/tmp2
 echo $freshcluster | grep 1
 if [ $? -eq 0 ];
 then 
#  sh iscsirefresh.sh
#  sh listingtargets.sh
  echo freshcluster=$freshcluster so zpool importing >>/root/tmp2
  #zpool import -a 2>/dev/null
   ./putzpool.py 2>/dev/null
  echo ran putzpool >>/root/tmp2
 fi
 touch /var/www/html/des20/Data/Getstatspid
fi
#zpool export -a
rm -rf /pacedata/forzfsping 2>/dev/null
echo fisniehd startzfs >>/root/tmp2
