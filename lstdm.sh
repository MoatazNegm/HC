#!/bin/sh
# QSD5.345: only the placeholders made by mkdm.sh (name of digits, a 'zero' table) are candidates for the stand-in of a lost
# mirror disk (selectspare.py solvedegradedraid).  It listed EVERY device-mapper device of the machine, so the host's own LVM
# volumes (dm-name-rl-home -> dm-2 here) were handed to 'zpool replace -f' as the new mirror leg; only 'device busy' (it is
# mounted) stopped ZFS from writing on /home.
for l in /dev/disk/by-id/dm-name-*
do
	[ -e "$l" ] || continue
	n=${l##*/dm-name-}
	case "$n" in
		''|*[!0-9]*) continue ;;
	esac
	dmsetup table "$n" 2>/dev/null | grep -q ' zero' || continue
	readlink "$l" | awk -F'/' '{print $NF}'
done
