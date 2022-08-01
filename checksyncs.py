#!/bin/python3.6
import subprocess, sys
from logqueue import queuethis
from etcdgetpy import etcdget as get
from etcdput import etcdput as put 
from broadcasttolocal import broadcasttolocal
from etcdputlocal import etcdput as putlocal 
from etcdgetlocal import etcdget as getlocal 
from Evacuatelocal import setall
from etcddel import etcddel as dels
from etcddellocal import etcddel as dellocal
from deltolocal import deltolocal
from usersyncall import usersyncall, oneusersync
from groupsyncall import groupsyncall, onegroupsync
from socket import gethostname as hostname

syncanitem = ['Snapperiod','user','group','host','passwd']
forReceivers = [ 'user', 'group' ]
nodeprops =  ['dataip','tz','ntp','gw','dns']
etcdonly = [ 'Snapperiod','sizevol', 'Partner','ready','alias', 'dataip','hostipsubnet', 'namespace','leader','allowedPartners','activepool','ipaddr','pools','poolnsnxt','volumes','localrun','logged','ActivePartners','config','pool','nextlead']
syncs = etcdonly + syncanitem + nodeprops
myhost = hostname()
actives = get('ActivePartners','--prefix')
Partners = get('Partners/','--prefix')
myip = get('ActivePartners/'+myhost)[0]
allsyncs = get('sync','request') 
donerequests = [ x for x in allsyncs if '/request/dhcp' in str(x) ] 
mysyncs = [ x for x in allsyncs if '/request/'+myhost in str(x) ] 
myrequests = [ x for x in allsyncs if x not in mysyncs ] 
leader = get('leader','--prefix')[0][0].replace('leader/','')
##### sync request template: sync/Operation/commandline_op1_op2_../request Operation_stamp###########
##### synced template for request sync[0]/+node stamp #####################
##### initial sync for known nodes : sync/Operation/initial Operation_stamp #######################
##### synced template for initial sync for known nodes : sync/Operation/initial/node Operation_stamp #######################
##### delete request of same sync if ActivePartners qty reached #######################

def checksync(myip='nothing'):
 global syncs, syncanitem, forReceivers, nodeprops, etcdony, myhost, allsyncs, hostip, actives
 for sync in syncs:
  if hostip='initial':
   from time import time as timestamp
   stamp = int(timestamp() + 3600)
   put('sync/'+sync+'/'+'initial/request',str(stamp)) 
   put('sync/'+sync+'/'+'initial/request/'+myhost,str(stamp)) 
  return
 for syncinfo in myrequests:
   syncleft = syncinfo[0]
   syncright = syncinfo[1]
   sync = syncleft.split('/')[1]
   cmdinfo = syncleft.split('/')(2).split('_')
   if sync in etcdonly:
     if cmdline[0] == 'Add':
      syncitem=get(sync,cmdline[1])
      putlocal(myip,syncitem[0],syncitem[1])
     else:
      dellocal(myip,sync,cmdline[1])
     if 'Snapperiod' in sync:
      from etctocron import etctocron
      etctocron()
   elif sync == 'user':
     oneusersync(cmdinfo[0],cmdinfo[1])
   elif sync == 'group':
     onegroupsync(cmdinfo[0],cmdinfo[1])
   elif sync == 'evacuatehost':
    setall(cmdinfo[0],cmdinfo[1],cmdinfo[2])
   elif sync in nodeprops:
    cmdline='/TopStor/pump.sh HostManualconfig'+sync+'local '
    result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
   else:
    print('there is a sync that is not defined:',sync)
    return
      
   put(syncleft+'/'+myhost, syncright)
   if myhost != leader:
    putlocal(myip, syncleft+'/'+myhost, syncright)
    putlocal(syncleft, syncright)
   if myhost != leader
    donerequests = [ x for x in donerequests if '/request/'+myhost not in str(x) ] 
    localdones = getlocal(myip, 'sync', '/request/dhcp')
    for done in donerequests:
     if done not in str(localdones):
      putlocal(myip, done[0],done[1])
      
 
if __name__=='__main__':
 checksync(*sys.argv[1:])
