#!/bin/sh
cd /TopStor
rb=`/bin/git branch | grep \* | awk '{print $2}'`
rbs=`/bin/git branch | sed 's/\*/ /g' `
echo $rb $rbs
