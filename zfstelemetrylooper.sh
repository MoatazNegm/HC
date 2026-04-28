#!/usr/bin/sh
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`

zfstelemetry() {
    /TopStor/zfs_telemetry.py $leaderip $myhost 1>/root/zfstelemetry.log 2>/root/zfstelemetryerr.log
}

while true 
do
    echo "Running ZFS telemetry check..."
    zfstelemetry
    sleep 5
done
