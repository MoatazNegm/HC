#!/usr/bin/sh
# The whole script is one block so sh has parsed it completely before it runs: the pull below
# replaces /pace and /TopStor, this file included.
{
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
# pull the primary's branch and commit before restarting, so this node joins on the same software
swip=`/pace/etcdget.py 10.11.11.253 tojoinsw/$myhost`
swbranch=`/pace/etcdget.py 10.11.11.253 tojoinbr/$myhost`
echo $swip | grep '\.'
if [ $? -eq 0 ] && [ ${#swbranch} -gt 3 ];
then
	cp /TopStor/joinpull.sh /root/joinpull.run
	sh /root/joinpull.run $swip $swbranch
	rm -f /root/joinpull.run
else
	echo no software to pull from the primary .... joining with the local software
fi
cd /pace
./etcddel.py 10.11.11.253 possible/$myhost
/TopStor/docker_setup.sh reboot
exit
}
