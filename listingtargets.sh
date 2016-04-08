iscsimapping='/pace/iscsimapping'
declare -a hosts=(`iscsiadm  -m session | awk -F'com.' '{print $2}' | awk -F':' '{print $1}'`)
declare -a disks=(`iscsiadm -m session -P3 | grep "scsi disk" | awk -F'State' '{print $1}' | awk -F'disk ' '{print $2}' | awk '{print $1}'` )
declare -a scsi=(`ls -l /dev/disk/by-id/ | grep scsi | grep -v part | awk -F'scsi-' '{print $2}' | awk -F'->' '{print $1}'`)
i=0;
rm -r $iscsimapping 2>/dev/null
for host in "${hosts[@]}"; do
 echo "$host" ${disks[$i]} ${scsi[$i]} >> $iscsimapping;
 i=$((i+1));
done

