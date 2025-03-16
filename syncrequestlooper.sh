#!/usr/bin/bash
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
syncrequest() {
cd /pace
/pace/checksyncs.py syncrequest $leaderip $myhost 1>/root/syncreq.log 2>/root/syncreqerr.log 
}

while true 
do
 syncrequest
 sleep 2 
done

