#!/usr/bin/sh
leaderip=echo $@ | awk '{print $1}'
myhost=echo $@ | awk '{print $2}'
selectimport() {
cd /pace
/pace/selectimport.py $leaderip $myhost 1>/root/selectimport.log 2>/root/selectimporterr.log 
}

while true 
do
 echo another round
 selectimport
 sleep 5 
done
