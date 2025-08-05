#!/bin/bash

leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`

retryvolumedelete() {
cd /pace
/pace/retryvolumedelete.sh $leaderip $myhost 1>/root/retryvolumedelete.log 2>/root/retryvolumedeleterr.log
}

while true; do
    echo "another round"
    retryvolumedelete
    sleep 9
done

