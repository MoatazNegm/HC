#!/bin/sh
######################
#exit
##########################
cd /pace
# QSD5.344: no CHAP secret in the debug copy of the arguments (argument 7)
echo $@ | awk '{ if (NF >= 7) $7 = "****"; print }' > /root/addzfsvol
#/pace/addzfsvolumeastarget.sh $pool'/'${vol} $ipaddr $portalport $targetiqn $chapuser $chappas
pool=`echo $@ | awk '{print $1}'`
vol=`echo $@ | awk '{print $2}'`
ipaddr=`echo $@ | awk '{print $3}'`
portalport=`echo $@ | awk '{print $4}'`
target=`echo $@ | awk '{print $5}'`
chapuser=`echo $@ | awk '{print $6}'`
chappas=`echo $@ | awk '{print $7}'`
# QSD5.344 (QC test 653): CHAP of the LUN.  NoCHAP (or nothing) = no CHAP; the pair MoatazNegm/MezoAdmin is the value every
# volume got before QSD5.344 (it was never asked for: authentication=0), so it means no CHAP too.  The API stores the
# secret encrypted ('enc~...'), it is decrypted only here, for targetcli.
nochap=0
case "$chapuser" in ''|NoCHAP|nochap|-) nochap=1 ;; esac
[ "$chapuser" = 'MoatazNegm' ] && [ "$chappas" = 'MezoAdmin' ] && nochap=1
if [ $nochap -eq 0 ]; then
 chappas=`/TopStor/secretmask.py phrasedec chap "$chappas"`
 [ -n "$chappas" ] || nochap=1
fi
lunid=`echo $@ | awk '{print $8}'`
# container flavour: no udev, the zvol node and its /dev/zvol link are made here (see czvoldev.sh)
[ -f /TopStor/flavor.sh ] && . /TopStor/flavor.sh
is_container 2>/dev/null && /pace/czvoldev.sh
disk=`ls -l /dev/zvol/${pool}/$vol | awk -F'/' '{print $NF}'`
echo disk $disk
#chapuser='iqn.1991-05.com.microsoft:desktop-jckvhk3'
#chapuser='MoatazNegm'
#chappass='MezoPass1234'
myhost=`hostname -s`;
change=0
#declare -a iscsitargets=(`cat /pacedata/iscsitargets | awk '{print $2}' `;
#target='iqn.1991-05.com.microsoft:desktop-jckvhk3'
#target='iqn.1994-05.com.redhat:dhcp13038'
#disk='zd0'
ipdom=`echo $ipaddr | sed 's/\.//g'`
diskids=$disk'-'$myhost'-'$vol
iqn='.2016-03.com.'$ipdom':data'
targetcli ls iscsi/ | grep ".$ipdom:data" &>/dev/null
if [ $? -ne 0 ]; then
 targetcli iscsi/ create iqn.2016-03.com.${ipdom}:data &>/dev/null
fi
pdisk=`targetcli ls backstores/block`
echo $pdisk | grep $disk 
if [ $? -ne 0 ];
then 
 targetcli backstores/block create $diskids /dev/$disk
 echo targetcli backstores/block create $diskids /dev/$disk
fi
#tpg='tpg'$portalport
tpg='tpg1'

#targetcli iscsi/iqn${iqn} create $portalport  
targetcli iscsi/iqn${iqn} set global auto_add_mapped_luns=false
targetcli iscsi/iqn.2016-03.com.$ipdom:data/${tpg}/portals delete 0.0.0.0 3260
targetcli iscsi/iqn${iqn}/${tpg}/luns/ create /backstores/block/$diskids  
targetcli iscsi/iqn${iqn}/${tpg}/acls/ create $target
echo targetcli iscsi/iqn${iqn}/${tpg}/acls/ create $target
cluns=`targetcli iscsi/iqn${iqn}/${tpg}/acls/$target ls`
echo $cluns | grep $diskids 
if [ $? -ne 0 ];
then
 # the number of LUNs already mapped for this initiator (the old 'echo $cluns | wc -l' always counted one line = 1)
 nextlun=`targetcli iscsi/iqn${iqn}/${tpg}/acls/$target ls | grep -c mapped_lun`
 echo targetcli iscsi/iqn${iqn}/${tpg}/acls/$target = $nextlun
 targetcli iscsi/iqn${iqn}/${tpg}/acls/$target create mapped_lun=$nextlun tpg_lun_or_backstore=/backstores/block/$diskids write_protect=0
 echo targetcli iscsi/iqn${iqn}/${tpg}/acls/$target create mapped_lun=$nextlun tpg_lun_or_backstore=/backstores/block/$diskids write_protect=0
fi
targetcli iscsi/iqn${iqn}/${tpg} set attribute demo_mode_write_protect=0 
targetcli iscsi/iqn${iqn}/${tpg} set attribute cache_dynamic_acls=1
# only the initiators listed on the LUN (the acls created above) may log in: generate_node_acls=1 gave every other IQN a dynamic ACL with all LUNs mapped
targetcli iscsi/iqn${iqn}/${tpg} set attribute generate_node_acls=0
# QSD5.344: CHAP is set on the initiator's ACL (generate_node_acls=0: the ACLs are what is checked; the old tpg-level
# userid/password were never used).  One target per address: authentication of the target is on while any ACL of it
# has a CHAP user, so a LUN without CHAP never switches it off for a LUN with CHAP on the same address.  'NULL' clears
# a CHAP value in LIO.
targetcli iscsi/iqn${iqn}/${tpg} set auth userid=NULL password=NULL >/dev/null 2>&1   # the old hard-coded tpg pair
if [ $nochap -eq 0 ]; then
 targetcli iscsi/iqn${iqn}/${tpg}/acls/$target set auth userid=$chapuser password=$chappas >/dev/null
 targetcli iscsi/iqn${iqn}/${tpg} set attribute authentication=1
 echo chap on for $target
else
 targetcli iscsi/iqn${iqn}/${tpg}/acls/$target set auth userid=NULL password=NULL >/dev/null 2>&1
 cfsacls=/sys/kernel/config/target/iscsi/iqn${iqn}/tpgt_1/acls
 if [ -d $cfsacls ]; then
  chapacls=`cat $cfsacls/*/auth/userid 2>/dev/null | grep -v '^NULL$' | grep -c .`
  if [ "$chapacls" -eq 0 ]; then
   targetcli iscsi/iqn${iqn}/${tpg} set attribute authentication=0
  else
   targetcli iscsi/iqn${iqn}/${tpg} set attribute authentication=1
  fi
 else
  targetcli iscsi/iqn${iqn}/${tpg} set attribute authentication=0      # no configfs view: the behaviour before QSD5.344
 fi
 echo chap off for $target
fi
targetcli iscsi/iqn.2016-03.com.$ipdom:data/${tpg}/portals create $ipaddr $portalport 
targetcli saveconfig
 #targetcli saveconfig /pacedata/targetconfig
