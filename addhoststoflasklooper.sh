#!/usr/bin/sh
leaderip=`echo $@ | awk '{print $1}'`
addhosts() {
 cd /pace
 /pace/addhoststoflask.sh $leaderip 1>/root/addhoststoflask.log 2>/root/addhoststoflask.log 
}

while true 
do
 echo another round
 addhosts
 sleep 60 
done
