#!/usr/local/bin/zsh
disk=$1
cd /mnt
mkdir /mnt/newsys
#mount /dev/${disk}1 /mnt/newsys
#rsync -aAXHv --exclude 'mnt' --exclude={"usr/ports/*","p1/*","dev/*","proc/*","sys/*","tmp/*","run/*","/mnt/*","media/*","lost+found"} /boot /mnt/newsys

#umount /mnt/newsys
mount /dev/${disk}2 /mnt/newsys
rsync -aAXHv --exclude 'mnt' --exclude={"boot/*","usr/ports/*","p1/*","dev/*","proc/*","sys/*","tmp/*","run/*","/mnt/*","media/*","lost+found"} / /mnt/newsys
umount /mnt/newsys
