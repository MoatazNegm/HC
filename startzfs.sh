cd /pace
iscsimapping='/pacedata/iscsimapping';
runningpools='/pacedata/pools/runningpools';
myip=`/sbin/pcs resource show CC | grep Attributes | awk '{print $2}' | awk -F'=' '{print $2}'`
result=`./nodesearch.py $myip`
echo $result | grep nothing 
if [ $? -ne 0 ];
then
 exit
fi
systemctl stop etcd 
./etccluster.py
systemctl start etcd
myhost=`hostname -s`
hostnam=`cat /TopStordata/hostname`
poollist='/pacedata/pools/'${myhost}'poollist';
lastreboot=`uptime -s`
seclastreboot=`date --date="$lastreboot" +%s`
secrunning=`cat $runningpools | grep runningpools | awk '{print $2}'`
 ./addtargetdisks.sh
lsblk -Sn | grep LIO &>/dev/null
if [ $? -ne 0 ]; then
sleep 2
fi
if [ -z $secrunning ]; then
 echo hithere: $lastreboot : $seclastreboot
 secdiff=222;
else
 secdiff=$((seclastreboot-secrunning));
fi
if [ $secdiff -ne 0 ]; then
 echo runningpools $seclastreboot > $runningpools
 ./keysend.sh &>/dev/null
 ccnic=`pcs resource show CC | grep nic\= | awk -F'nic=' '{print $2}' | awk '{print $1}'`
 pcs resource create IPinit ocf:heartbeat:IPaddr nic="$ccnic" ip="10.11.11.254" cidr_netmask=24
 rm -rf /TopStor/key/adminfixed.gpg && cp /TopStor/factory/factoryadmin /TopStor/key/adminfixed.gpg
 zpool export -a
 sh iscsirefresh.sh
 sh listingtargets.sh
 touch /var/www/html/des20/Data/Getstatspid
fi
 zpool export -a
systemctl start smb
