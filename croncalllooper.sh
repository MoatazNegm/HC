#!/usr/bin/bash

leaderip=`echo $@ | awk '{print $1}'`
cronto() {
cd /pace
/pace/croncall.py $leaderip 
}

while true 
do
 echo another round
 cronto 
 sleep 9 
done

