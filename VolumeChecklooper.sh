#!/usr/bin/sh
volumecheckpy() {
	cd /TopStor
    	leaderip=`docker exec etcdclient /TopStor/etcdgetlocal.py leaderip`
 	/pace/VolumeCheck.py $leaderip `hostname` 
}

while true;
do
 volumecheckpy
 sleep 5 
done

