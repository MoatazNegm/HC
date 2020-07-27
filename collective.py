#!/bin/python3.6
import subprocess, socket, binascii, pika 
from threading import Thread
from etcdput import etcdput as put
from etcdget import etcdget as get 
from broadcast import broadcast as broadcast 
from os import listdir
from os import remove 
from poolall import getall as getall
from os.path import getmtime
import sys
import logmsg


def fixpool(*args):
 myhost=socket.gethostname()
 pools=get('fixpool','--prefix')
 for p in pools:
  pool=p[0].replace('fixpool/','')
  host=get('pools/'+pool)[0]
  if myhost==host:
   cmdline='/TopStor/fixpool.sh '+pool
   result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE) 
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
 myhost=socket.gethostname()
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
 myhost=hostname()
 dt=datetime.datetime.now().strftime("%m/%d/%Y")
 tm=datetime.datetime.now().strftime("%H:%M:%S")
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

def logmsg(*args):
 z=[]
 knowns=[]
 myhost=hostname()
 dt=datetime.datetime.now().strftime("%m/%d/%Y")
 tm=datetime.datetime.now().strftime("%H:%M:%S")
 z=['/TopStor/logmsg2.sh', dt, tm, myhost ]
 for arg in args:
  z.append(arg)
 print('z=',z)
 leaderinfo=get('leader','--prefix')
 knowninfo=get('known','--prefix')
 leaderip=leaderinfo[0][1]
 for k in knowninfo:
  knowns.append(k[1])
 print('leader',leaderip) 
 print('knowns',knowns) 
 msg={'req': 'msg2', 'reply':z}
 print('sending', leaderip, str(msg),'recevreply',myhost)
 sendhost(leaderip, str(msg),'recvreply',myhost)
 for k in knowninfo:
  sendhost(k[1], str(msg),'recvreply',myhost)
  knowns.append(k[1])
def isprimary(*args):
 ispd={}
 ispd['trythis']=trythis
 ispd['fixpool']=fixpool
 ispd['logqueue']=logqueue
 ispd['logmsg']=logmsg
 ispd['sendhost']=sendhost
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
    if cmndnm in ispd.keys():
     x=Thread(target=ispd[cmndnm],name=cmndnm,args=tuple(cmnd.split()[2:]))
     x.start()

def putzpool(*args):
 return

def checklocal(*args):
 return 

def checkinit(*args):
 return

if __name__=='__main__':
 x=Thread(target=isprimary,name='isprimary',args=(1,1))
 x.start()
 x=Thread(target=putzpool,name='putzpool',args=(1,1))
 x.start()
 x=Thread(target=checklocal,name='checklocal',args=(1,1))
 x.start()
 x=Thread(target=checkinit,name='checkinit',args=(1,1))
 x.start()
