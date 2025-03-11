#!/usr/bin/bash

leader=`echo $@ | awk '{print $3}'`
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
myhostip=`echo $@ | awk '{print $4}'`
zpoolto() {
cd /pace
/pace/zpooltoimport.py $leader $leaderip $myhost $myhostip 
}

while true 
do
 echo another round
 zpoolto 
 sleep 9 
done

