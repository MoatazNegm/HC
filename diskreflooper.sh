#!/usr/bin/bash

leader=`echo $@ | awk '{print $3}'`
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
myhostip=`echo $@ | awk '{print $4}'`
[ -f /TopStor/flavor.sh ] && . /TopStor/flavor.sh
# container flavour: cdiskref.sh (caddtargetdisks.sh, loop disks of /root/loopdisks); physical: diskref.sh (addtargetdisks.sh,
# SCSI disks only, lsblk -S).  The container exporter on a physical node exported every zvol (zdN) as a cluster disk
# zdN-<host>, which held the iSCSI volume open: its own backstore was never made and the volume could not be deleted.
diskref() {
cd /pace
if is_container 2>/dev/null; then
	/pace/cdiskref.sh $leader $leaderip $myhost $myhostip
else
	/pace/diskref.sh $leader $leaderip $myhost $myhostip
fi
}

while true 
do
 echo another round
 diskref 
 sleep 5 
done

