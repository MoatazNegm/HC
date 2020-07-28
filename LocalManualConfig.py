#!/bin/python3.6
import subprocess,sys, datetime
from etcdget import etcdget as get
from etcdput import etcdput as put
from broadcasttolocal import broadcasttolocal 
from ast import literal_eval as mtuple
import logmsg
def config(*bargs):
 enpdev='enp0s8'
 with open('/root/HostManualconfigtmp2','w') as f:
  f.write('bargs:'+str(bargs)+'\n')
 with open('/TopStordata/Hostprop.txt') as f:
  oldbarg=f.read()
 oldbarg=oldbarg.replace('"','').replace('{','').replace('}','').replace(',',' ')
 oldarg=oldbarg.split()
 arg=bargs
 with open('/root/HostManualconfigtmp2','a') as f:
  f.write('arg:'+str(arg)+'\n')
 change={}
 owner=''
 msg={}
 for x in arg[:-1]:
  if x not in oldarg:
   x=x.split(':')
   change[x[0]]=x[1]
   change['old'+x[0]]=x[1]
   for y in oldarg:
    if x[0] in y and 'host' not in y:
     y=y.split(':')
     change['old'+x[0]]=y[1]
  if 'hostname' in x:
    x=x.split(':')
    owner=x[1]
 if len(change) < 1: 
  return
 logmsg.sendlog('HostManual1002','info',arg[-1])
 with open('/root/HostManualconfigtmp2','a') as f:
  f.write('change:'+str(change)+'\n')
######### changing name ###############
 if 'name' in change:
  logmsg.sendlog('HostManual1st5','info',arg[-1],change['oldname'],change['name'])
  put('alias/'+owner,change['name'])
  broadcasttolocal('alias/'+owner,change['name'])
  logmsg.sendlog('HostManual1su5','info',arg[-1],change['oldname'],change['name'])
######### changing cluster address ###############
 if 'mgmtip' in change:
  if 'mgmtsubnet' in change:
   subnet=change['mgmtsubnet']
   oldsubnet=change['oldmgmtsubnet']
  else:
   subnet=oldsubnet=24
   for y in oldarg:
    if 'mgmtsubnet' in y:
     y=y.split(':')
     subnet=oldsubnet=y[1]
  logmsg.sendlog('HostManual1st7','info',arg[-1],change['oldmgmtip']+'/'+oldsubnet,change['mgmtip']+'/'+subnet)
 with open('/root/HostManualconfigtmp2','a') as f:
  f.write('run HostManualconfigNameSpace:'+change['mgmtip']+change['oldmgmtip']+subnet+oldsubnet+'\n')
  cmdline=['/TopStor/HostManualconfigNameSpace',change['mgmtip'],change['oldmgmtip'],subnet,oldsubnet]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)
  put('namespace/mgmtip',change['mgmtip']+'/'+subnet)
  broadcasttolocal('namespace/mgmtip',change['mgmtip']+'/'+subnet)
  logmsg.sendlog('HostManual1su7','info',arg[-1],change['oldmgmtip']+'/'+oldsubnet,change['mgmtip']+'/'+subnet)
######### changing box address ###############
 if 'addr' in change:
  if 'addrsubnet' in change:
   subnet=change['addrsubnet']
   oldsubnet=change['oldaddrsubnet']
  else:
   subnet=oldsubnet=24
   for y in oldarg:
    if 'addrsubnet' in y:
     y=y.split(':')
     subnet=oldsubnet=y[1]
     
  logmsg.sendlog('HostManual1st6','info',arg[-1],change['oldaddr']+'/'+oldsubnet,change['addr']+'/'+subnet)
  cmdline=['/TopStor/HostManualconfigCC',change['addr'],change['oldaddr'],subnet,oldsubnet]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)
  logmsg.sendlog('HostManual1su6','info',arg[-1],change['oldaddr']+'/'+oldsubnet,change['addr']+'/'+subnet)
######### changing data address ###############
 if 'dataip' in change:
  if 'dataipsubnet' in change:
   subnet=change['dataipsubnet']
   oldsubnet=change['olddataipsubnet']
  else:
   subnet=oldsubnet=24
   for y in oldarg:
    if 'dataipsubnet' in y:
     y=y.split(':')
     subnet=oldsubnet=y[1]
  logmsg.sendlog('HostManual1st8','info',arg[-1],change['olddataip']+'/'+oldsubnet,change['dataip']+'/'+subnet)
  cmdline=['/TopStor/HostManualconfigDataIP',change['dataip'],change['olddataip'],subnet,oldsubnet]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)
  logmsg.sendlog('HostManual1su8','info',arg[-1],change['olddataip']+'/'+oldsubnet,change['dataip']+'/'+subnet)
#####################################################
  cmdline=['/TopStor/HostgetIPs']
 return 1

if __name__=='__main__':
 config(*sys.argv[1:])
