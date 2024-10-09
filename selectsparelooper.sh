#!/usr/bin/sh
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
selectspare() {
cd /pace
/pace/selectspare.py $leaderip $myhost 1>/root/selectspare.log 2>/root/selectsparerr.log 
}

while true 
do
 echo another round
 selectspare
 sleep 5 
done

