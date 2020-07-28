#!/bin/python3.6
import subprocess, socket, binascii, pika, sys
from threading import Thread
from threading import enumerate as tenumerate
from etcdput import etcdput as put
from etcdget import etcdget as get 
from etcddel import etcddel as deli 
from etcddellocal import etcddel as delilocal
from broadcast import broadcast as broadcast 
from os import listdir
from datetime import datetime
from poolall import getall as getall
from os.path import getmtime
import logmsg
from broadcasttolocal import broadcasttolocal as broadcasttolocal
from etcdgetlocal import etcdget as getlocal
from etcdputlocal import etcdput as putlocal 


threads={}
ispd={}

def putzpool(*args):
 threads['putzpool']=1
 perfmon=get('perfmon')
 if '1' in perfmon:
  stamp=int(datetime.now().timestamp())
  logqueue('putzpool.py','start','system',stamp)
 sitechange=0
 readyhosts=get('ready','--prefix')
 knownpools=[f for f in listdir('/TopStordata/') if 'pdhcp' in f and 'pree' not in f ]
 cmdline='/sbin/zpool status'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout
 sty=str(result)[2:][:-3].replace('\\t','').split('\\n')
 cmdline='/bin/lsscsi -is'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout
 lsscsi=[x for x in str(result)[2:][:-3].replace('\\t','').split('\\n') if 'LIO' in x ]
 freepool=[x for x in str(result)[2:][:-3].replace('\\t','').split('\\n') if 'LIO' in x ]
 periods=get('Snapperiod','--prefix')
 raidtypes=['mirror','raidz','stripe']
 raid2=['log','cache','spare']
 zpool=[]
 stripecount=0
 spaces=-2
 raidlist=[]
 disklist=[]
 lpools=[]
 ldisks=[]
 ldefdisks=[]
 linusedisks=[]
 lfreedisks=[]
 lsparedisks=[]
 lhosts=set()
 phosts=set()
 lraids=[]
 lvolumes=[]
 lsnapshots=[]
 poolsstatus=[]
 x=list(map(chr,(range(97,123))))
 drives=';sd'.join(x).split(';')
 drives[0]='sd'+drives[0]
 cmdline=['/sbin/zfs','list','-t','snapshot,filesystem','-o','name,creation,used,quota,usedbysnapshots,refcompressratio,prot:kind,available','-H']
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 zfslistall=str(result.stdout)[2:][:-3].replace('\\t',' ').split('\\n')
 #lists=[lpools,ldisks,ldefdisks,lavaildisks,lfreedisks,lsparedisks,lraids,lvolumes,lsnapshots]
 lists={'pools':lpools,'disks':ldisks,'defdisks':ldefdisks,'inusedisks':linusedisks,'freedisks':lfreedisks,'sparedisks':lsparedisks,'raids':lraids,'volumes':lvolumes,'snapshots':lsnapshots, 'hosts':lhosts, 'phosts':phosts}
 for a in sty:
  b=a.split()
  if len(b) > 0:
   b.append(b[0])
   if any(drive in str(b[0]) for drive in drives):
    for lss in lsscsi:
     if any('/dev/'+b[0] in lss for drive in drives):
      b[0]='scsi-'+lss.split()[6]
  if "pdhc" in str(b) and  'pool' not in str(b):
   raidlist=[]
   volumelist=[]
   zdict={}
   rdict={}
   ddict={}
   zfslist=[x for x in zfslistall if b[0] in x ]
   cmdline=['/sbin/zpool','list',b[0],'-H']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   zlist=str(result.stdout)[2:][:-3].split('\\t')
   cmdline=['/sbin/zfs','get','compressratio','-H']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE) 
   zlist2=str(result.stdout)[2:][:-3].split('\\t')
   if b[0] in knownpools:
    cachetime=getmtime('/TopStordata/'+b[0])
   else:
    cmdline='/sbin/zpool set cachefile=/TopStordata/'+b[0]+' '+b[0]
    subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
    cachetime='notset'
   poolsstatus.append(('pools/'+b[0],myhost))
   zdict={ 'name':b[0],'changeop':b[1], 'status':b[1],'host':myhost, 'used':str(zfslist[0].split()[6]),'available':str(zfslist[0].split()[11]), 'alloc': str(zlist[2]), 'empty': zlist[3], 'dedup': zlist[7], 'compressratio': zlist2[2],'timestamp':str(cachetime), 'raidlist': raidlist ,'volumes':volumelist}
   zpool.append(zdict)
   lpools.append(zdict) 
   for vol in zfslist:
    if b[0]+'/' in vol and '@' not in vol and b[0] in vol:
     volume=vol.split()
     volname=volume[0].split('/')[1]
     snaplist=[]
     snapperiod=[]
     snapperiod=[[x[0],x[1]] for x in periods if volname in x[0]]
     vdict={'fullname':volume[0],'name':volname, 'pool': b[0], 'host':myhost, 'creation':' '.join(volume[1:4]+volume[5:6]),'time':volume[4], 'used':volume[6], 'quota':volume[7], 'usedbysnapshots':volume[8], 'refcompressratio':volume[9], 'prot':volume[10],'snapshots':snaplist, 'snapperiod':snapperiod}
     volumelist.append(vdict)
     lvolumes.append(vdict['name'])
    elif '@' in vol and b[0] in vol:
     snapshot=vol.split()
     snapname=snapshot[0].split('@')[1]
     sdict={'fullname':snapshot[0],'name':snapname, 'volume':volname, 'pool': b[0], 'host':myhost, 'creation':' '.join(snapshot[1:4]+volume[5:6]), 'time':snapshot[4], 'used':snapshot[6], 'quota':snapshot[7], 'usedbysnapshots':snapshot[8], 'refcompressratio':snapshot[9], 'prot':snapshot[10]}
     snaplist.append(sdict)
     lsnapshots.append(sdict['name'])
  elif any(raid in str(b) for raid in raidtypes):
   spaces=len(a.split(a.split()[0])[0])
   disklist=[]
   rdict={ 'name':b[0], 'changeop':b[1],'status':b[1],'pool':zdict['name'],'host':myhost,'disklist':disklist }
   raidlist.append(rdict)
   lraids.append(rdict)
  elif any(raid in str(b) for raid in raid2):
   spaces=len(a.split(a.split()[0])[0])
   disklist=[]
   rdict={ 'name':b[0], 'changeop':'NA','status':'NA','pool':zdict['name'],'host':myhost,'disklist':disklist }
   raidlist.append(rdict)
   lraids.append(rdict)
  elif 'scsi' in str(b) or 'disk' in str(b) or '/dev/' in str(b) or (len(b) > 0 and 'sd' in b[0] and len(b[0]) < 5):
   diskid='-1'
   host='-1'
   size='-1' 
   devname='-1'
   disknotfound=1
   if  len(a.split('scsi')[0]) < (spaces+2) or (len(raidlist) < 1 and len(zpool)> 0):
    disklist=[]
    rdict={ 'name':'stripe-'+str(stripecount), 'pool':zdict['name'],'changeop':'NA','status':'NA','host':myhost,'disklist':disklist }
    raidlist.append(rdict)
    lraids.append(rdict)
    stripecount+=1
    disknotfound=1
   for lss in lsscsi:
    z=lss.split()
    if z[6] in b[0] and len(z[6]) > 3 and 'OFF' not in b[1] :
     diskid=lsscsi.index(lss)
     host=z[3].split('-')[1]
     lhosts.add(host)
     phosts.add(host)
     size=z[7]
     devname=z[5].replace('/dev/','')
     freepool.remove(lss)
     disknotfound=0
     break
   if disknotfound == 1:
     diskid=0
     host='-1'
     size='-1'
     devname=b[0]
   changeop=b[1]
   if host=='-1':
    raidlist[len(raidlist)-1]['changeop']='Warning'
    zpool[len(zpool)-1]['changeop']='Warning'
    changeop='Removed'
    sitechange=1
   ddict={'name':b[0],'actualdisk':b[-1], 'changeop':changeop,'pool':zdict['name'],'raid':rdict['name'],'status':b[1],'id': str(diskid), 'host':host, 'size':size,'devname':devname}
   disklist.append(ddict)
   ldisks.append(ddict)
 if len(freepool) > 0:
  raidlist=[]
  zdict={ 'name':'pree','changeop':'pree', 'available':'0', 'status':'pree', 'host':myhost,'used':'0', 'alloc': '0', 'empty': '0', 'dedup': '0', 'compressratio': '0', 'raidlist': raidlist, 'volumes':[]}
  zpool.append(zdict)
  lpools.append(zdict)
  disklist=[]
  rdict={ 'name':'free', 'changeop':'free','status':'free','pool':'pree','host':myhost,'disklist':disklist }
  raidlist.append(rdict)
  lraids.append(rdict)
  for lss in freepool:
   z=lss.split()
   diskid=lsscsi.index(lss)
   host=z[3].split('-')[1]
   if host not in str(readyhosts):
    continue
# #### commented for not adding free disks of freepool
   lhosts.add(host)
   size=z[7]
   devname=z[5].replace('/dev/','')
   ddict={'name':'scsi-'+z[6],'actualdisk':'scsi-'+z[6], 'changeop':'free','status':'free','raid':'free','pool':'pree','id': str(diskid), 'host':host, 'size':size,'devname':devname}
   disklist.append(ddict)
   ldisks.append(ddict)
 if len(lhosts)==0:
   lhosts.add('')
 if len(phosts)==0:
   phosts.add('')
 put('hosts/'+myhost+'/current',str(zpool))
 for disk in ldisks:
  if disk['changeop']=='free':
   lfreedisks.append(disk)
  elif disk['changeop'] =='AVAIL':
   lsparedisks.append(disk)
  elif disk['changeop'] != 'ONLINE': 
   ldefdisks.append(disk)
 put('lists/'+myhost,str(lists))
 xall=get('pools/','--prefix')
 x=[y for y in xall if myhost in str(y)]
 xnotfound=[y for y in x if y[0].replace('pools/','') not in str(poolsstatus)]
 xnew=[y for y in poolsstatus if y[0].replace('pools/','') not in str(x)]
 for y in xnotfound:
  if y[0] not in xall:
   dels(y[0].replace('pools/',''),'--prefix')
  else:
   dels(y[0])
 for y in xnew:
  put(y[0],y[1])
 if '1' in perfmon: 
  stamp=int(datetime.now().timestamp())
  logqueue('putzpool.py','stop','system',stamp)
 threads['putzpool']=0
 return
 
def fixpool(*args):
 threads['fixpool']=1
 pools=get('fixpool','--prefix')
 for p in pools:
  pool=p[0].replace('fixpool/','')
  host=get('pools/'+pool)[0]
  if myhost==host:
   cmdline='/TopStor/fixpool.sh '+pool
   result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE) 
 threads['fixpool']=0
 return

def syncthispartner(*args):
 thehost=args[0]
 for key in args[1:]:
  mylist=get(key,'--prefix')
  dellocal(thehost,key,'--prefix')
  for item in mylist:
   moditem=""
   restitem=""
   keysplit=item[0].split(key)
   if len(keysplit) > 1:
    restitem=keysplit[1]
   putlocal(thehost, key+restitem, item[1])
 return

def syncpartners(*args):
 knowns=[]
 knowninfo=get('known','--prefix')
 print('knwon',knowninfo)
 for k in knowninfo:
  for arg in args:
   delilocal(k[1],arg,'--prefix')
   etcdinfo=get(arg,'--prefix')
   for item in etcdinfo:
    putlocal(k[1],item[0],item[1])
 return

def syncthispool(*args):
 pool=args[0]
 bpoolfile=''
 with open('/TopStordata/'+pool,'rb') as f:
  bpoolfile=f.read()
  poolfile=binascii.hexlify(bpoolfile)
  broadcast('Movecache','/TopStordata/'+pool,poolfile) 
 return 

def syncmypools(*args):
 logmsg.sendlog('Zpst03','info','system')
 myhostpools=[]
 runningpools=[]
 readyhosts=get('ready','--prefix')
 myhostpools=getall(myhost)['pools']
 for pool in myhostpools:
  if pool['name']=='pree' :
   continue
  cachetime=getmtime('/TopStordata/'+pool['name'])
  if cachetime==pool['timestamp']:
    continue 
  bpoolfile=''
  with open('/TopStordata/'+pool['name'],'rb') as f:
   bpoolfile=f.read()
  poolfile=binascii.hexlify(bpoolfile)
  broadcast('Movecache','/TopStordata/'+pool['name'],str(poolfile)) 
 logmsg.sendlog('Zpsu03','info','system')
 return 

def trythis(*args):
 with open('/pacedata/trythis','w') as tr:
  tr.write('hi there hello')
 return
  
def sendhost(host, req, que, frmhst, port=5672):
 msg={'host': frmhst, 'req': req }
# creds=pika.PlainCredentials('rabb_'+frmhst,'YousefNadody')
 creds=pika.PlainCredentials('rabbmezo','HIHIHI')
 param=pika.ConnectionParameters(host, port, '/', creds)
 conn=pika.BlockingConnection(param)
 chann=conn.channel()
 try: 
  chann.basic_publish(exchange='',routing_key=que, body=str(msg))
  return 0
 except:
  return 1

def logqueue(*args):
 z=[]
 knowns=[]
 dt=datetime.now().strftime("%m/%d/%Y")
 tm=datetime.now().strftime("%H:%M:%S")
 z=['/TopStor/logqueue2.sh', dt, tm, myhost ]
 for arg in args:
  z.append(arg)
 leaderinfo=get('leader','--prefix')
 knowninfo=get('known','--prefix')
 leaderip=leaderinfo[0][1]
 for k in knowninfo:
  knowns.append(k[1])
 msg={'req': 'queue', 'reply':z}
 sendhost(leaderip, str(msg),'recvreply',myhost)
 for k in knowninfo:
  sendhost(k[1], str(msg),'recvreply',myhost)
  knowns.append(k[1])
 return

def logmsgthis(*args):
 logmsg.sendlog(*args)
 return

def etcdput(*args):
 put(*args)
 return

def etcdputlocal(*args):
 putlocal(*args)
 return

def etcddellocal(*args):
 delilocal(*args)
 return

def etcddel(*args):
 deli(*args)
 return

def broadcastthis(*args):
 broadcast(*args)
 return

def HostgetIPs(*args):
 threads['HostgetIPs']=1
 cmdline='/TopStor/HostgetIPs'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 threads['HostgetIPs']=0
 return

def runningetcdnodes(*args):
 threads['runningetcdnodes']=1
 ip=args[0]
 cmdline=['etcdctl','-w','json','--endpoints='+ip+':2379','member','list']
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 serverstatus=result.stdout
 serverstatus=str(serverstatus)[2:]
 serverstatus=serverstatus[:-3]
 etcdfile=open('/pacedata/runningetcdnodes.txt','w')
 etcdfile.write(serverstatus)
 etcdfile.close()
 etcdfile=open('/var/www/html/des20/Data/runningetcdnodes.txt','w')
 etcdfile.write(serverstatus)
 etcdfile.close()
 threads['runningetcdnodes']=0
 return

def addknown(*args):
 threads['addknown']=1
 allow=get('allowedPartners')
 if 'notallowed' in str(allow):
  threads['addknown']=0
  return
 perfmon=get('perfmon')
 if '1' in perfmon:
  stamp=int(datetime.now().timestamp())
  logqueue('addknown.py','start','system',stamp)
 possible=get('possible','--prefix')
 if possible != []:
  for x in possible:
   if 'yestoall' not in str(allow):
    if x[0].replace('possible','') not in str(allow):
     Active=get('AcivePartners','--prefix')
     if x[0].replace('possible','') not in str(Active):
      threads['addknown']=0
      return 
   knowns=get('known','--prefix')
   putlocal(x[1],'configured','yes')
   frstnode=get('frstnode')
   if x[0].replace('possible','') not in frstnode[0]:
    newfrstnode=frstnode[0]+'/'+x[0].replace('possible','')
    put('frstnode',newfrstnode)
   put('known/'+x[0].replace('possible',''),x[1])
   put('ActivePartners/'+x[0].replace('possible',''),x[1])
   broadcasttolocal('ActivePartners/'+x[0].replace('possible',''),x[1])
   put('nextlead',x[0].replace('possible','')+'/'+x[1])
   cmdline=['/sbin/rabbitmqctl','add_user','rabb_'+x[0].replace('possible',''),'YousefNadody']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   cmdline=['/sbin/rabbitmqctl','set_permissions','-p','/','rabb_'+x[0].replace('possible',''),'.*','.*','.*']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   deli('losthost/'+x[0].replace('possible',''))
   put('change/'+x[0].replace('possible','')+'/booted',x[1])
   put('tosync','yes')
   broadcast('broadcast','/TopStor/pump.sh','syncnext.sh','nextlead','nextlead')
   if x[0].replace('possible','') in str(knowns):
    put('allowedPartners','notoall')
    deli('possible',x[0])
    logmsg.sendlog('AddHostsu01','info',arg[-1],name)
    if '1' in perfmon:
     stamp=int(datetime.now().timestamp())
     logqueue('AddHost.py','finished',args[-1],stamp)
 if '1' in perfmon:
  stamp=int(datetime.now().timestamp())
  logqueue('addknown.py','stop','system',stamp)
 return

def tosync(*args):
 threads['tosync']=1
 totalen=len(get('ready','--prefix'))+len(get('lost','--prefix'))
 apcount=len(get('ActivePartners','--prefix'))
 if totalen != apcount:
  print('total',totalen,apcount)
  put('tosync','yes')
 tos=get('tosync','--prefix')
 if 'yes' in str(tos):
  deli('tosync','--prefix')
  syncpartners(*args)
 threads['tosync']=0
 return

def setnamespace(*args):
 threads['setnamespace']=1
 nslist=get('namespace','--prefix')
 if 'mgmtip' not in str(nslist):
  put('namespace/mgmtip','192.168.43.7/24')
  nslist=get('namespace','--prefix')
 ns=(x for x in nslist)
 for arg in args:
  try: 
   nsn=next(ns)
  except: 
   threads['setnamespace']=0
   return
  cmdline='/sbin/pcs resource create '+nsn[0].replace('namespace/','')+' ocf:heartbeat:IPaddr2 nic='+arg+' ip='+nsn[1].split('/')[0]+' cidr_netmask='+nsn[1].split('/')[1]+' op monitor on-fail=restart'
  subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
  cmdline='/sbin/pcs resource group add namespaces '+nsn[0].replace('namespace/','')
  subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 threads['setnamespace']=0
 return

def syncthistoleader(*args):
 leaderip=get('leader','--prefix')[0][1]
 deli(args[1],args[2])
 etcdinfo=getlocal(args[0],args[1],args[2])
 for item in etcdinfo:
   put(item[0],item[1])
 return

def checkknown(*args):
 myhost=args[0]
 myip=args[1]
 myconfig=getlocal(myip,'configured')
 if 'yes' in str(myconfig):
  put('possible'+myhost,myip)
 else:
  put('toactivate'+myhost,myip)
 return 

ispd.update({'tosync':tosync, 'addknown':addknown, 'runningetcdnodes':runningetcdnodes, 'trythis':trythis })
ispd.update({'fixpool':fixpool, 'logqueue':logqueue, 'logmsg':logmsg, 'sendhost':sendhost,'etcdput':etcdput })
ispd.update({'putzpool':putzpool, 'HostgetIPs':HostgetIPs, 'broadcastthis':broadcastthis})
ispd.update({'etcddel':etcddel, 'etcdputlocal':etcdputlocal, 'etcddellocal':etcddellocal})
ispd.update({'checkknown':checkknown, 'syncthistoleader':syncthistoleader, 'setnamespace':setnamespace})
ispd.update({'syncthispartner':syncthispartner})

threads.update({'tosync':0, 'addknown':0, 'runningetcdnodes':0, 'trythis':0, 'fixpool':0, 'logqueue':0})
threads.update({'etcddel':0,'fixpool':0, 'logmsg':0, 'sendhost':0, 'etcdput':0, 'broadcastthis':0})
threads.update({'setnamespace':0, 'etcdputlocal':0, 'etcddellocal':0, 'putzpool':0, 'HostgetIPs':0})
threads.update({'syncthispartner':0, 'checkknown':0, 'syncthistoleader':0})


def isprimaryt(*args):
 global threads
 global ispd
 cmdline='rm -rf  /pacedata/isprimary'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 cmdline='mkfifo -m 660 /pacedata/isprimary'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 while True: 
  with open('/pacedata/isprimary') as colv:
   colvlst=colv.readlines()
   colvlst.sort(key=lambda x:int(x.split()[0]))
   for cmnd in colvlst:
    cmndnm=cmnd.split()[1]
    if cmndnm in ispd.keys() and threads[cmndnm]==0 and threads['runningetcdnodes']==0:
     x=Thread(target=ispd[cmndnm],name=cmndnm,args=tuple(cmnd.split()[2:]))
     x.start()

def fixpoolt(*args):
 global threads
 global ispd
 cmdline='rm -rf  /pacedata/fixpool'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 cmdline='mkfifo -m 660 /pacedata/fixpool'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 while True: 
  with open('/pacedata/fixpool') as colv:
   colvlst=colv.readlines()
   colvlst.sort(key=lambda x:int(x.split()[0]))
   for cmnd in colvlst:
    cmndnm=cmnd.split()[1]
    if cmndnm in ispd.keys() and threads[cmndnm]==0 and threads['runningetcdnodes']==0:
     x=Thread(target=ispd[cmndnm],name=cmndnm,args=tuple(cmnd.split()[2:]))
     x.start()
 threads['addknown']=0
 return

def putzpoolt(*args):
 global threads
 global ispd
 cmdline='rm -rf  /pacedata/putzpool'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 cmdline='mkfifo -m 660 /pacedata/putzpool'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 while True: 
  with open('/pacedata/putzpool') as colv:
   colvlst=colv.readlines()
   colvlst.sort(key=lambda x:int(x.split()[0]))
   for cmnd in colvlst:
    cmndnm=cmnd.split()[1]
    if cmndnm in ispd.keys() and threads[cmndnm]==0 and threads['runningetcdnodes']==0:
     x=Thread(target=ispd[cmndnm],name=cmndnm,args=tuple(cmnd.split()[2:]))
     x.start()
 return

def etcdallt(*args):
 global threads
 global ispd
 cmdline='rm -rf  /pacedata/etcdall'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 cmdline='mkfifo -m 660 /pacedata/etcdall'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 while True: 
  with open('/pacedata/etcdall') as colv:
   colvlst=colv.readlines()
   colvlst.sort(key=lambda x:int(x.split()[0]))
   for cmnd in colvlst:
    cmndnm=cmnd.split()[1]
    if cmndnm in ispd.keys():
     x=Thread(target=ispd[cmndnm],name=cmndnm,args=tuple(cmnd.split()[2:]))
     x.start()
 return


def checklocalt(*args):
 return 

def checkinitt(*args):
 return

if __name__=='__main__':
 myhost=socket.gethostname()
 x=Thread(target=isprimaryt,name='checkprimary',args=(1,1))
 x.start()
 x=Thread(target=fixpoolt,name='thepoolfix',args=(1,1))
 x.start()
 x=Thread(target=putzpoolt,name='listpools',args=(1,1))
 x.start()
 x=Thread(target=etcdallt,name='etcdall',args=(1,1))
 x.start()
 x=Thread(target=checklocalt,name='checklocal',args=(1,1))
 x.start()
 x=Thread(target=checkinitt,name='checkinit',args=(1,1))
 x.start()
 print(tenumerate())
