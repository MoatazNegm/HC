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
# QSD5.352 r10c (QC proof S-1 / G-2, suspected): an initiator list of two had 0 ACLs on the address 60 s after a
# volumes/config (542.1, 547.2), and after a take-over one of two LUNs of one address was not mapped (554.1); nothing
# said why.  Every call leaves one line per step in /root/iscsitarget.log (time, volume, zvol, backstore, initiator,
# the mapped LUNs of the initiator at the end).  A volume whose zvol node is not there is not exported half
# (a backstore '-<host>-<vol>' with no device was made before): it is logged and the call ends with rc 1.
tlog() { [ -f /root/iscsitarget.log ] && [ `stat -c %s /root/iscsitarget.log 2>/dev/null || echo 0` -gt 5000000 ] && mv -f /root/iscsitarget.log /root/iscsitarget.log.1; echo "`date '+%F %T'` $pool/$vol $*" >> /root/iscsitarget.log; }
if [ -z "$disk" ]; then
 tlog "NOT EXPORTED: no zvol device for /dev/zvol/$pool/$vol (disk '$disk'), initiator $target"
 exit 1
fi
[ -b /dev/$disk ] || tlog "WARNING: /dev/$disk (the zvol of /dev/zvol/$pool/$vol) is not a block device here"
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
# QSD5.352 r10p (QC proof 10o F2, 550.1/.2): two runs for one address at the same time (a create and the iSCSI
# watchdog's re-export, or two volumes of one address) both found no LUN of the backstore and both made one: zd16 was
# mapped as lun1 AND lun2.  Container flavour: the runs of one target are serialized (flock, 120 s; held to the end of
# this script) and the tpg LUN is made only when no LUN of the target maps the backstore yet.  Physical unchanged.
if is_container 2>/dev/null; then
 mkdir -p /var/lock 2>/dev/null
 exec 8>>/var/lock/addzfsvolumeastarget.$ipdom.lock
 flock -w 120 8 || tlog "WARNING: the lock of target $ipdom was not taken in 120 s, $diskids goes on without it"
fi
targetcli ls iscsi/ | grep ".$ipdom:data" &>/dev/null
if [ $? -ne 0 ]; then
 targetcli iscsi/ create iqn.2016-03.com.${ipdom}:data &>/dev/null
fi
pdisk=`targetcli ls backstores/block`
# QSD5.352 r10 (QC 652): the backstore of THIS volume by its full name; 'grep $disk' matched zd1 inside zd16-<host>-<other>,
# so a new LUN on zd1 got no backstore of its own and was never exported or mapped
echo "$pdisk" | grep -q -- "o- $diskids "
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
if is_container 2>/dev/null && targetcli ls iscsi/iqn${iqn}/${tpg}/luns 2>/dev/null | grep -qF "[block/$diskids "; then
 tlog "backstore $diskids already has a LUN of iqn${iqn}, no second one (r10p F2)"
else
 targetcli iscsi/iqn${iqn}/${tpg}/luns/ create /backstores/block/$diskids
fi
targetcli iscsi/iqn${iqn}/${tpg}/acls/ create $target
echo targetcli iscsi/iqn${iqn}/${tpg}/acls/ create $target
targetcli ls iscsi/iqn${iqn}/${tpg}/acls/$target >/dev/null 2>&1 || tlog "ACL of '$target' could not be made on iqn${iqn} (not a valid initiator name?)"
cluns=`targetcli iscsi/iqn${iqn}/${tpg}/acls/$target ls`
echo $cluns | grep $diskids 
if [ $? -ne 0 ];
then
 # QSD5.352 r10 (QC 652): the lowest mapped LUN number this initiator does not use yet.  The count of mapped LUNs
 # (QSD5.344) was taken as the next number: after a LUN in the middle was deleted, the count named a number still in
 # use (mapped_lun1 of the next LUN), the create failed or doubled a mapping and the new LUN was not mapped right.
 used=" `targetcli iscsi/iqn${iqn}/${tpg}/acls/$target ls 2>/dev/null | grep -o 'mapped_lun[0-9][0-9]*' | sed 's/mapped_lun//' | tr '\n' ' '`"
 nextlun=0
 while echo "$used" | grep -q " $nextlun "; do nextlun=$((nextlun+1)); done
 echo targetcli iscsi/iqn${iqn}/${tpg}/acls/$target = $nextlun
 targetcli iscsi/iqn${iqn}/${tpg}/acls/$target create mapped_lun=$nextlun tpg_lun_or_backstore=/backstores/block/$diskids write_protect=0
 echo targetcli iscsi/iqn${iqn}/${tpg}/acls/$target create mapped_lun=$nextlun tpg_lun_or_backstore=/backstores/block/$diskids write_protect=0
fi
tlog "zvol $disk backstore $diskids address $ipaddr:$portalport initiator $target: `targetcli ls iscsi/iqn${iqn}/${tpg}/acls/$target 2>&1 | grep -o 'mapped_lun[0-9]* [^]]*' | tr '\n' ';'`"
targetcli iscsi/iqn${iqn}/${tpg} set attribute demo_mode_write_protect=0 
targetcli iscsi/iqn${iqn}/${tpg} set attribute cache_dynamic_acls=1
# only the initiators listed on the LUN (the acls created above) may log in: generate_node_acls=1 gave every other IQN a dynamic ACL with all LUNs mapped
targetcli iscsi/iqn${iqn}/${tpg} set attribute generate_node_acls=0
# QSD5.344: CHAP is set on the initiator's ACL (generate_node_acls=0: the ACLs are what is checked; the old tpg-level
# userid/password were never used).  One target per address: authentication of the target is on while any ACL of it
# has a CHAP user, so a LUN without CHAP never switches it off for a LUN with CHAP on the same address.
# QSD5.346: a CHAP value is cleared with an EMPTY value ('set auth userid='): rtslib_fb (2.1.76) refuses the word 'NULL'
# ("'NULL' is not a permitted value") and writes 'NULL' to configfs itself for an empty value.  One field per call and
# the empty field last on the line: the configshell parser takes the next word as the value ('userid= password='
# sets userid to the text 'password=').
chapclear() {
 targetcli "$1" set auth password= >/dev/null 2>&1
 targetcli "$1" set auth userid= >/dev/null 2>&1
}
chapclear iscsi/iqn${iqn}/${tpg}   # the old hard-coded tpg pair
if [ $nochap -eq 0 ]; then
 targetcli iscsi/iqn${iqn}/${tpg}/acls/$target set auth userid=$chapuser password=$chappas >/dev/null
 targetcli iscsi/iqn${iqn}/${tpg} set attribute authentication=1
 echo chap on for $target
else
 chapclear iscsi/iqn${iqn}/${tpg}/acls/$target
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
