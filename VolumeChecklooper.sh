#!/usr/bin/bash

leader=`echo $@ | awk '{print $3}'`
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
myhostip=`echo $@ | awk '{print $4}'`
volumecheckpy() {
	cd /pace
 	/pace/VolumeCheck.py $leaderip $myhost 
}

while true;
do
 sleep 10 
 volumecheckpy
done

