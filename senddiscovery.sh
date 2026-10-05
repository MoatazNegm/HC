#!/usr/bin/sh
cd /pace
myhost=`hostname`
myhostip=`docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip`
while true
do
	/pace/etcdput.py 10.11.11.253 possible/$myhost $myhostip
	clusterip=`/pace/etcdget.py 10.11.11.253 tojoin/$myhost`
	echo $clusterip | grep '\.'
	if [ $? -eq 0 ];
	then

		break
	fi
	echo ./etcdput.py 10.11.11.253 possible/$myhost $myhostip
	sleep 3
done
echo will join the cluster $clusterip
echo yes_fromsenddtarget > /root/nodeconfigured
echo $clusterip > /root/newcaddr
./etcddel.py 10.11.11.253 possible/$myhost
/TopStor/docker_setup.sh reboot
