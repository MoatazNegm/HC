#!/bin/sh
cd /pace
node=`echo $@ | awk '{print $1}'`
pcs cluster localnode remove $node;
pcs cluster reload corosync;
crm_node -R $node --force;
