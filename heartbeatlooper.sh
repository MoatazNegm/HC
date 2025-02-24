#!/usr/bin/sh
heartbeat () {
cd /pace
/pace/heartbeat.py 
}
while true;
do
 heartbeat 
 sleep 1 
done

