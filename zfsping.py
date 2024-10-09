#!/usr/bin/python3
from checkleader import checkleader
from remknown import remknown
from poolall import getall as getall
from getload import getload
from sendhost import sendhost
import subprocess,sys, logmsg, os
from croncall import croncall
from logqueue import queuethis
from etcddel import etcddel as etcddel
from etcdgetpy import etcdget as get
from etcdgetlocalpy import etcdget as getlocal
from time import time as stamp
from time import sleep
from etcdput import etcdput as put 
#from addknown import addknown
from putzpool import putzpool, initputzpool
from activeusers import activeusers
from addactive import addactive
from selectimport import selectimport
from zpooltoimport import zpooltoimport
#from selectspare import spare2  
def spare2(x,y,*others):
 return
from checksyncs import syncrequest, initchecks
from VolumeCheck import volumecheck
from multiprocessing import Process
from concurrent.futures import ProcessPoolExecutor
from heartbeat import heartbeat
from etcdspace import space

os.environ['ETCDCTL_API']= '3'
ctask = 1
dirtydic = { 'pool': 0, 'volume': 0 } 
croncallrun = 0
refresh = 0
selectsparerun = 0 
volrun = 0
poolrun = 0
importrun = 0 

def heartbeatpls():
 global leader, myhost
 try:
  cleader = leader
  leader, leaderip = heartbeat()
  if leader != cleader:
   print('######################################################################### heartbeat')
   cleader = leader
   refreshall()
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in heartbeat:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
 

def dosync(leader,*args):
 put(*args)
 put(args[0]+'/'+leader,args[1])

def iscsiwatchdogproc():
 try:
  cmdline='/pace/iscsiwatchdog.sh'
  result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in iscsiwatchdogproc:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
def croncallproc():
 global leaderip, croncallrun, leader, myhost, myhostip
 if croncallrun == 1:
    print('bypassing croncall')
    return
 print('running croncall')
 croncallrun = 1
 croncall(leaderip)    
 croncallrun = 0

def fapiproc():
  cmdline='/pace/fapilooper.sh' 
  result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')

def putzpoolproc():
 global leaderip, leader, myhost, myhostip
 try:
  putzpool()
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in putzpool:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')

def addactiveproc():
 global leader, myhost
 try:
  addactive(leader,myhost)
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in addactive:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')

def selectimportproc():
 global leader, leaderip, myhost, myhost, myhostip, etcdip, importrun
 if importrun == 1:
    print('bypassing selectimport')
    return
 importrun = 1

 try:
  allpools=get(etcdip, 'pools/','--prefix')
  selectimport(myhost,allpools,leader)
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in selectimport:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
 importrun = 0 
   

def zpooltoimportproc():
 global leader, myhost, leaderip, myhostip, etcdip, dirtydic, poolrun
 if poolrun == 1:
    print('bypassing poolimporting')
    return
 poolrun = 1
 dirtypool = int(dirtydic['pool'])
 if int(dirtydic['pool']) >= 10:
  dirtydic['pool'] = 0
  return
 dirtypool += 1 
 put(etcdip, 'dirty/pool', str(dirtypool))
 dirtydic['pool'] = dirtypool
 try:
  zpooltoimport(leader, leaderip, myhost, myhostip, etcdip)
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in zpooltoimport:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
 poolrun = 0
 
def volumecheckproc():
 global leader, myhost, leaderip, myhostip, etcdip, dirtydic, volrun
 if volrun == 1:
    print('bypassing volumeimporting')
    return
 volrun = 1
 dirtyvol = int(dirtydic['volume'])
 if dirtyvol > 12  :
  dirtydic['volume'] = 0
  return
 dirtydic['volume'] = dirtyvol + 1 
 put(etcdip, 'dirty/volume', str(dirtydic['volume']))
 try:
  etcds = get(etcdip, 'volumes','--prefix')
  replis = get(etcdip, 'replivol','--prefix')
  volumecheck(etcds, replis)
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in volumecheckproc:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
 volrun = 0
def refreshall():
 global leaderip, leader, myhost, myhostip, etcdip, refresh
 while refresh == 1:
  sleep(1)
 refresh = 1
 print('putzpool',leader, leaderip,myhost,myhostip)
 putzpool()
 allpools=get(etcdip, 'pools/','--prefix')
 #selectimport(myhost,allpools,leader)
 zpooltoimport(leader, myhost)
 etcds = get(etcdip,'volumes','--prefix')
 replis = get(etcdip, 'replivol','--prefix')
 putzpool()
 volumecheck(etcds, replis)
 spare2(leader, myhost)
 putzpool()
 refresh = 0 
def selectspareproc():
 global leader, myhost, selectsparerun
 if selectsparerun == 1:
    print('bypassing selectspare')
    return
 selectsparerun = 1
 try:
  putzpool()
  clsscsi = 'nothing'
  spare2(leader, myhost)
  putzpool()
  cmdline='lsscsi -is'
  lsscsi=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
  if clsscsi != lsscsi:
   clsscsi = lsscsi
   selectsparerun = 0 
   refreshall()
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in selectspare:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  selectsparerun = 0 
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
 selectsparerun = 0 

def syncrequestproc():
 global leader, myhost
 try:
  syncrequest(leader, myhost)
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in syncrequest:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')

def remknownproc():
 global leader, myhost
 try:
  remknown(leader,myhost) 
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in remknown:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')

#def addknownproc():
# global leader, myhost
# try:
#  if myhost == leader:
#   addknown(leader,myhost)
# except Exception as e:
#  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
#  print(' in addknown:',e)
#  with open('/root/pingerr','a') as f:
#   f.write(e)
#  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')

def activeusersproc():
 global leader, myhost
 try:
  activeusers(leader, myhost)
 except Exception as e:
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')
  print(' in activeusers:',e)
  with open('/root/pingerr','a') as f:
   f.write(e)
  print('EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE')

def spaceopti():
    global etcdip
    space(etcdip)



#loopers = [ addknownproc, remknownproc, activeusersproc, iscsiwatchdogproc, putzpoolproc, addactiveproc, selectimportproc, zpooltoimportproc , volumecheckproc, selectspareproc , syncrequestproc ]
loopers = [ zpooltoimportproc, volumecheckproc, selectspareproc , putzpoolproc, spaceopti, croncallproc ]
#loopers = [ zpooltoimportproc, volumecheckproc, selectspareproc , putzpoolproc]

def CommonTask(task):
 print("''''''''' task started",task,"'''''''''''''''''''''''''''''''''''''''")
 #if 'selectspare' in str(task):
 # print('############################thisis the task will fail')
 # task()
 task()
 #sleep(2)
 print("''''''''' task ended",task,"'''''''''''''''''''''''''''''''''''''''",flush=True)

i = 0
def lazyloop():
 global i
 while True:
  resyyult = loopers[i % len(loopers)]
  yield result 
  i = i + 1
 return next() 


def lazylooper():
    x = 0
    while True:
        yield loopers[x]
        x = x + 1
        if x == len(loopers):
         x = 0
def zfspinginit():
    global etcdip, leader, leaderip, myhost, myhostip
    myhostip = get(leaderip, 'ready/'+myhost)[0]
    leader = get(leaderip, 'leader')[0]
    #leaderinfo = checkleader('leader','--prefix').stdout.decode('utf-8').split('\n')
    #leader = leaderinfo[0].split('/')[1]
    #leaderip = leaderinfo[1]
    #cleader = leader
    if myhost == leader:
        etcdip = leaderip
    else:
        etcdip = myhostip
    initputzpool(leader, leaderip, myhost, myhostip)
    #space(etcdip)
    spare2('init', leader, leaderip, myhost, myhostip, etcdip)
    #remknown('init', leader, leaderip, myhost, myhostip, etcdip)
    zpooltoimport('init', leader, leaderip, myhost, myhostip, etcdip)
    volumecheck('init', leader, leaderip, myhost, myhostip, etcdip)
   

if __name__=='__main__':
 print('hihihih')
 selectsparerun = 0 
 croncallrun = 0
 refresh = 0 
 leaderip = sys.argv[1]
 myhost = sys.argv[2]
 zfspinginit()
 dirty = get(etcdip, 'dirty','--prefix')
 for dic in dirtydic:
  if dic not in str(dirty):
   print('dic',dic)
   put(etcdip, 'dirty/'+dic,'1000')
 print('etcd',etcdip)
 stopat = 0 
 counter = 1 
 while True:
  zfspinginit()
  with ProcessPoolExecutor() as e:
    for i in range(len(loopers)):
     if stopat not in range(len(loopers)):
        stopat = 0 
     zload = getload(leaderip,myhost)
     if zload > 65 and counter > 0:
        print('still load high',zload,'counter',counter,'process number',i, 'stopped at',stopat)
        sleep(2)
        counter = counter +1 
        if counter < 30:
            continue
        else: 
            counter = -len(loopers) 
            zload = 40
     else:
        counter += 1
     print('fixing i to ',stopat)
     args = loopers[stopat]
     print('starting a new task',stopat,args)
     res = e.submit(CommonTask,args)
     sleep(2)
     dirty = get(etcdip, 'dirty','--prefix')
     for dirt in dirty:
      dirtydic[dirt[0].split('/')[1]] = dirt[1]
     print('---------dirty------',dirty)
     print('load ok', zload)
     stopat = stopat+1
 exit()

