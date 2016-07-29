#!/usr/local/bin/zsh
disk=$1
mkfs.xfs -f  /dev/${disk}1
mkfs.xfs -f /dev/${disk}2
mkswap /dev/${disk}3
swapon /dev/${disk}3
