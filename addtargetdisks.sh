#!/usr/bin/sh
######################
#exit
##########################
echo $@ > /root/addtargets
bootdisk='sda'
bootdiskf='/TopStordata/bootdiskf'
if [ ! -f $bootdiskf ];
then
 echo $bootdisk > $bootdiskf
else
 bootdisk=`cat $bootdiskf`
fi
bootpart=`lsblk -o NAME,MOUNTPOINT | grep boot | awk '{print $1}'`
bootdisk=${bootpart:2:-1}; 
echo bootdisk is $bootdisk
cd /pace
etcdip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
actives=`/pace/etcdget.py $etcdip Active --prefix`
change=0
#echo hi1 $myhost>> /root/targetadd
#declare -a iscsitargets=(`cat /pacedata/iscsitargets | awk '{print $2}' `);
initialtarget=`targetcli ls | wc -l`
myip=`docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip`
mycluster=`nmcli conn show mycluster | grep ipv4.addresses | awk '{print $2}' | awk -F'/' '{print $1}'`
declare -a iscsitargets=(`docker exec etcdclient /pace/iscsiclients.py $etcdip | grep target | awk -F'/' '{print $2}'`);
currentdisks=`targetcli ls /iscsi`
disks=(`lsblk -nS -o name,serial,vendor | grep -vw $bootdisk | grep -v sr0 |  grep -v LIO | awk '{print $1}'`)
nodes=(`docker exec etcdclient /TopStor/etcdgetlocal.py Active --prefix | awk -F'Partners/' '{print $2}' | awk -F"'" '{print $1}'`)
diskids=`lsblk -nS -o name,serial,vendor | grep -vw $bootdisk | grep -v sr0 | grep -v LIO | awk '{print $1" "$2}'`
mappedhosts=`targetcli ls /iscsi | grep Mapped`;
targets=`targetcli ls backstores/block | grep -v deactivated |  grep dev | awk -F'[' '{print $2}' | awk '{print $1}'`
blocks=`targetcli ls backstores/block `
# filter the new iscsi disks that were not part of the backstore , then create them if needed
for ddisk in  "${disks[@]}"; do
	echo $blocks | grep $ddisk >/dev/null
	if [ $? -ne 0 ];
	then
		echo $ddisk not a part in the targets
		ordinary=`lsscsi -i | grep -w $ddisk | grep -v LIO | awk '{print $NF}'`
		#scsidisk=`ls -l /dev/disk/by-id/ | grep -w $ddisk | grep -v part | grep scsi | grep -v LIO | grep -v SLS | awk '{print $9}'`
		scsidisk=`ls -l /dev/disk/by-id/ | grep -w $ddisk | grep -v part | grep scsi-$ordinary | awk '{print $9}'`
  		targetcli backstores/block create ${ddisk}-${myhost} /dev/disk/by-id/$scsidisk
		
	else
		echo $ddisk is a part in the targets backstore
	fi
done
declare -a newdisks=();
# check and create the t1 entry of myhost
targetcli ls iscsi/ | grep $myhost:t1 >/dev/null
if [ $? -ne 0 ];
then
 targetcli iscsi/ create iqn.2016-03.com.$myhost:t1
else
	echo t1 entry is already create for $myhost
fi
tpgs1=(`targetcli ls /iscsi | grep iqn`) 
# check if my ip was changed so I have a wrong tpg1, of it my tpg was not created before. so I create the write tpg 
targetcli ls iscsi/iqn.2016-03.com.$myhost:t1/tpg1/portals | grep $myip &>/dev/null
if [ $? -ne 0 ]; then
 targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals delete 0.0.0.0 3260
 targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals ls | grep 3266 | awk -F'o-' '{print $2}' | awk -F':' '{print $1}'
 oldip=`targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals ls | grep 3266 | awk -F'o-' '{print $2}' | awk -F':' '{print $1}'`
 targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals delete $oldip 3260
 echo oldip=$oldip
 #targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals delete$olidp 3266
 targetcli iscsi/iqn.2016-03.com.$myhost:t1/tpg1/portals create $myip 3266
else
  echo my tpg1 portal is already created
fi
targetcli /iscsi/iqn.2016-03.com.${myhost}:t1 set global auto_add_mapped_luns=true
i=0;
# check if there is a new disk to create it as devdisk-myhsot in the backstore block
for ddisk in "${disks[@]}"; do
 devdisk=$ddisk 
 idisk=`echo "$diskids" | grep -w $ddisk | awk '{print $2}'`
 echo $currentdisks | grep $devdisk-$myhost &>/dev/null
 if [ $? -ne 0 ]; then
  pdisk=`ls /dev/disk/by-id/ | grep $idisk | grep -v part | grep scsi | head -1`
  targetcli backstores/block create ${devdisk}-${myhost} /dev/disk/by-id/$pdisk
  change=1
  tpgs=(`targetcli ls /iscsi | grep iqn | grep TPG | grep ':t1' | awk -F'iqn' '{print $2}' | awk '{print $1}'`)
  for iqn in "${tpgs[@]}"; do
   ################################targetcli iscsi/iqn${iqn}/tpg1/luns/ create /backstores/block/${devdisk}-${myhost}  
   change=1
  done
 else
  echo $devdisk-$myhost is already created in the backstores/block 
 fi
done;

#######check if one of the hosts is new and was not mapped before
for target in "${iscsitargets[@]}"; do
 echo $mappedhosts | grep $target &>/dev/null
 if [ $? -ne 0 ]; then
  change=1
 fi
done

targetcli /iscsi/iqn.2016-03.com.${myhost}:t1 set global auto_add_mapped_luns=true
tpgs1=(`targetcli ls /iscsi | grep iqn | grep TPG | grep ':t1'`)
tpgs=(`targetcli ls /iscsi | grep iqn | grep TPG | grep ':t1' | awk -F'iqn' '{print $2}' | awk '{print $1}'`)

# mapping the luns to every iqn in the tpgs create the missing ones and create also the 
for node in "${nodes[@]}"; do
 for ddisk in "${disks[@]}"; do
	for iqn in "${tpgs[@]}"; do
 		targetcli iscsi/iqn${iqn}/tpg1/acls/ ls | grep redhat:$node >/dev/null
		if [ $? -ne 0 ];
		then
  			targetcli iscsi/iqn${iqn}/tpg1/acls/ create iqn.1994-05.com.redhat:$node
		 	echo An tpg1/acl is create for the node $node
		else
		 	echo the node $node already has an acl entry the tpgs 
		fi
 		devdisk=`echo $ddisk | awk '{print $1}'`
 		targetcli iscsi/iqn${iqn}/tpg1/luns/ ls | grep  ${devdisk}-${myhost}  >/dev/null
		if [ $? -eq 0 ];
		then
			echo iqn$iqn has a map for $devdisk-$myhost
		else
			echo iqn$iqn is not mapped to  $devdisk
   			targetcli iscsi/iqn${iqn}/tpg1/luns/ create /backstores/block/${devdisk}-${myhost}  
		fi
	done
 done
done
#echo hi8 >> /root/targetadd
targetcli /iscsi/iqn.2016-03.com.${myhost}:t1 set global auto_add_mapped_luns=false

#echo hi9 >> /root/targetadd
targetcli saveconfig

endingtarget=`targetcli ls | wc -l`
if [[ $initialtarget != $endingtarget ]];
then
  stamp=`date +%s%N`
fi
