cd /pace
iscsimapping='/pacedata/iscsimapping';
iscsitargets='/pacedata/iscsitargets';
systemctl stop iscsi
while read -r  hostline ; do
 host=`echo $hostline | awk '{print $2}'`
 rm -rf /var/lib/iscsi/nodes/iqn.2016-03.com.${host}:t1 
 rm -rf /var/lib/iscsi/send_targets/* 
 rm -rf /var/lib/iscsi/nodes/${host}* &>/dev/null
done < $iscsitargets
systemctl start iscsi
