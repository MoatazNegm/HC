#!/usr/bin/python3
import subprocess,sys, os
#from socket import gethostname as hostname
from levelthis import levelthis
from logqueue import queuethis, initqueue
from raidrank import getraidrank
from ast import literal_eval as mtuple
from etcdgetpy import etcdget as get
from etcdput import etcdput as put
from etcddel import etcddel as dels 
from fastselect import optimizedisks
from putzpool import putzpool, initputzpool
from copy import deepcopy
#from deltolocal import deltolocal as delstolocal
#from poolall import getall as getall
from allphysicalinfo import getall 
from time import sleep
from sendhost import sendhost
from time import time as stamp
#from syncpools import syncmypools
os.environ['ETCDCTL_API']= '3'
newop=[]
disksvalue=[]
usedfree=[]
myhost = '' 

def dosync(*args):
 global leader, leaderip, myhost, myhostip, etcdip
 put(leaderip, *args)
 put(leaderip, args[0]+'/'+leader,args[1])

def solvefaultyreplace(raid):
    global leader, leaderip, myhost, myhostip, etcdip
    replacedict = dict()
    print('solving faulty replace')
    for disk in raid['disklist']:
        # QSD5.345: only pool disks carry 'replacingroup' (putzpool.py); a disk of the free / spare-cache list has none
        replacingroup = disk.get('replacingroup', '')
        if 'replac' in replacingroup and 'replac' not in disk['name']:
            if replacingroup not in replacedict:
                replacedict[replacingroup] = list()
            replacedict[replacingroup].append(disk)
    flag = 0 
    off_disk = 0
    for replacegroup in replacedict:
        for disk in replacedict[replacegroup]:
            if 'OFF' in disk['status'] and 'dm-' in disk['name'] and off_disk == 1:
                cmdline2=['/sbin/zpool', 'detach',raid['pool'], disk['name']]
                forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                flag = 1
                break 
            if 'OFF' in disk['status'] and 'dm-' in disk['name']:
                off_disk =1
            if 'UNAVA' in disk['status']:
                cmdline2=['/sbin/zpool', 'detach',raid['pool'], disk['actualdisk']]
                forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                print('dddddddddd',disk)
                flag = 1
                break
    return flag
    
def mustattach(cmdline,disksallowed,raid):
   global leader, leaderip, myhost, myhostip, etcdip
   print('################################################')
   if len(disksallowed) < 1 : 
    return 'na'
   print('helskdlskdkddlsldssd#######################')
   cmd=cmdline.copy()
   spare=disksallowed
   print('spare',spare)
   print('###########################')
   spareplsclear=get(etcdip, 'clearplsdisk/'+spare['actualdisk'])
   spareiscleared=get(etcdip, 'cleareddisk/'+spare['actualdisk']) 
   if spareiscleared[0] != spareplsclear[0] or spareiscleared[0] == '_1':
    print('asking to clear')
    put(etcdip, 'clearplsdisk/'+spare['actualdisk'],spare['host'])
    dels(etcdip , 'cleareddisk/'+spare['actualdisk']) 
    hostip=get(etcdip, 'ready/'+spare['host'])
    z=['/TopStor/Zpoolclrrun',spare['actualdisk']]
    msg={'req': 'Zpool', 'reply':z}
    print(hostip[0], str(msg),'recvreply',myhost)
    sendhost(hostip[0], str(msg),'recvreply',myhost)
    print('returning')
    print('raid',raid)
    return 'wait' 
   dels(etcdip, 'clearplsdisk/'+spare['actualdisk']) 
   dels(etcdip, 'cleareddisk/'+spare['actualdisk']) 
   print('cmd',cmd)
   print('raidname',raid)
   if 'stripe' in raid['name']:
    print('############start attaching')
    cmd = cmd+[raid['disklist'][0]['name'],'/dev/disk/by-id/'+spare['name']] 
    print('thecmd',' '.join(cmd))
    res = subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode !=0:
     print('somehting went wrong', res.stderr.encode())
    else:
     print(' the most suitable disk is attached')
    return
   dmcmd = 'zpool status '+raid['pool']
   dmstup = subprocess.run(dmcmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode('utf-8')
   if 'dm-' in dmstup:
    print('somthing wrong, there is already a stup found for this degraded group')
    return
   dmstup = 'dm-'+dmstup.split('dm-')[1].split(' ')[0]
   cmd = cmd+[dmstup, '/dev/disk/by-id/'+spare['name']] 
   res = subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE) 
   #cmd = ['systemctl', 'restart', 'zfs-zed']
   #subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   with open('/root/dmproblem','w') as f:
    f.write('cmdline '+ " ".join(cmd)+'\n')
    f.write('result: '+res.stdout.decode()+'\n')
    f.write('result: '+res.stderr.decode()+'\n')
   print('result', res.stderr.decode())    
   #if int(res.stderr.decode()) == 0:
   dels('needtoreplace', spare['name'])
   return 
 
 
def norm(val):
 units={'B':1/1024**2,'K':1/1024, 'M': 1, 'G':1024 , 'T': 1024**2 }
 if type(val)==float:
  return val
 if val[-1] != 'B':
  return float(val) 
 else:
  if val[-2] in list(units.keys()):
   return float(val[:-2])*float(units[val[-2]])
  else:
   return float(val[:-1])*float(units['B'])



def getbalance(diskA,diskB,balancetype,hostcounts,onlinedisks=[]):
 global newop
 global leader, leaderip, myhost, myhostip, etcdip
  
 raidhosts=hostcounts.copy()
 w=0
 if 'free' in diskA['changeop']:
  w=1
########## Stripe  DiskA free policy: Any###################################
 if 'stripe' in diskB['raid']: # if stripe calcualte the 
  print('spare1')
  if norm(diskB['size']) > norm(diskA['size']):
   print('spare1_1')
   w=1000000
   return w
########## Stripe  DiskA free policy: Useability###############################
  if 'useable' in balancetype:
   print('spare1_2')
   sizediff=10*(norm(diskA['size'])-norm(diskB['size'])) # tendency to same size
   w+=sizediff+int(diskA['host'] in diskB['host'])
   return w
########## Stripe  DiskA free policy: Availability##############################
  else:
   print('spare1_3')
   sizediff=(norm(diskA['size'])-norm(diskB['size']))
   w+=sizediff+10*int(diskA['host'] in diskB['host'])    # tendency to otherhost
   return w
######### RAID DiskB online DiskA free policy: useability #####################
 elif 'free' in diskA['changeop'] and 'ONLINE' in diskB['status']:# DiskB online
  print('spar2')
  if 'useable' in balancetype:
   print('spar2_1')
   sizediff=(norm(diskA['size'])-norm(diskB['size'])) # tendency to same size
 ########### Mirror and DiskB online diskA free policy: useability ############
   if 'mirror' in diskB['raid']:    # useable type not to mirror large disks
    print('spar2_2')
    if norm(diskA['size']) > norm(diskB['size']):
     print('spar2_3')
     w=100002
     return w
    print('spar2_4')
    w+=10*sizediff+int(diskA['host'] in diskB['host'])
    return w
 ########### RAID and DiskB online diskA free policy: Availability #########
  else:
   print('spar2_5')
   minB=min(onlinedisks,key=lambda x:norm(x['size']))
   if norm(minB['size']) > norm(diskA['size']):
    print('spar2_6')
    w=1000000
    return w
   print('spar2_7')
   raidhosts[diskA['host']]+=1
   raidhosts[diskB['host']]-=1
   if 'raidz' in diskB['raid']:
    print('spar2_8')
    sizediff=norm(diskA['size'])-norm(diskB['size']) 
    if diskA['host']==diskB['host'] and norm(diskA['size']) >= norm(diskB['size']) :
     print('spar2_9')
     w=2200000
     return w
   if 'raidz1' in diskB['raid']:
    print('spar2_10')
    if raidhosts[diskA['host']] > 1:
     print('spar2_11')
     w=2000000
     return w
    elif raidhosts[diskA['host']]==1 and raidhosts[diskB['host']]<1:
     print('spar2_12')
     w=2100000
     return w
    elif raidhosts[diskA['host']]<=1 and raidhosts[diskB['host']] >=raidhosts[diskA['host']]:
     print('spar2_13')
     w+=sizediff+10*int(raidhosts[diskA['host']]-raidhosts[diskB['host']])
     return w
    else:
      print('spar2_14')
      print('Error',raidhosts)

   elif 'raidz2' in diskB['raid']:
    print('spar2_15')
    if raidhosts[diskA['host']] > 2:
     print('spar2_16')
     w=2000000
     return w
    elif raidhosts[diskA['host']]==2 and raidhosts[diskB['host']]<2:
     print('spar2_17')
     w=2100000
     return w
    elif raidhosts[diskA['host']]==1 and raidhosts[diskB['host']]<0:
     print('spar2_18')
     w=2200000
     return w
    elif raidhosts[diskA['host']]<=2 and raidhosts[diskB['host']] >=raidhosts[diskA['host']]:
     print('spar2_19')
     w+=sizediff+10*int(raidhosts[diskA['host']]-raidhosts[diskB['host']])
     return w
    else:
      print('spar2_20')
      print('Error',raidhosts)
    
 ########### Mirror and DiskB online diskA free policy: Availability #########
   elif 'mirror' in diskB['raid']:
    print('spar2_21')
    if raidhosts[diskA['host']]==2:
     w=3100000
     return w
    print('spar2_22')
    sizediff=norm(diskA['size'])-norm(diskB['size']) 
    if sizediff >= 0 and hostcounts[diskB['host']]==1:
     print('spar2_23')
     w=3200000
     return w
    print('spar2_24')
    w+=sizediff+10*int(diskA['host'] in diskB['host'])
    return w
########### RAID and DiskB online diskA in Raid policy: Any #########
 elif diskB['raid'] in diskA['raid'] and 'ONLINE' in diskB['status']:  
  print('spare3')
  sizediff=norm(diskA['size'])-norm(diskB['size']) 
 ########### Mirror and DiskB online diskA in Raid policy: Useability #########
  if 'useable' in balancetype:  # tendency not to take the large size
   print('spare3_1')
   if 'mirror' in diskB['raid']:
    print('spare3_2')
    w+=10*sizediff+int(diskA['host'] in diskB['host'])
    return w
 ########### RAID and DiskB online diskA in Raid policy: Availability ########
  else:
   print('spare3_3')
   if 'raidz' in diskB['raid']:
    w=3000000
    return w
   elif 'mirror' in diskB['raid']:
    print('spare3_4')
    w=3000000
    #w+=sizediff+10*int(diskA['host'] in diskB['host'])
    return w 
########### RAID DiskB Failed diskA free policy: Any ########
 elif 'free' in diskA['changeop'] and 'ONLINE' not in diskB['status']:
  print('spare4')
  minB=min(onlinedisks,key=lambda x:norm(x['size']))
  sizediff=norm(diskA['size'])-norm(minB['size']) 
  minB=min(onlinedisks,key=lambda x:norm(x['size']))
########### RAIDZ DiskB Failed diskA free policy: Any ########
  if 'raidz' in diskB['raid']:
   print('spare4_1')
   try:
    print('spare4_2')
    raidhosts[diskA['host']]+=1
   except:
    print('spare4_3')
    raidhosts[diskA['host']]=1
   print('spare4_4')
   minB=min(onlinedisks,key=lambda x:norm(x['size']))
   if norm(minB['size']) > norm(diskA['size']):
    print('spare4_5')
    w=1000000
    return w
   print('spare4_6')
   sizediff=norm(diskA['size'])-norm(diskB['size']) 
 ########### RAID DiskB Failed diskA free policy: Useability ########
  if 'useable' in balancetype:
   print('spare4_7')
   if 'raidz1' in diskB['raid']:
    print('spare4_8')
    w+=10*sizediff+int(raidhosts[diskA['host']]-1)
    return w
   elif 'raidz2' in diskB['raid']:
    print('spare4_9')
    w+=10*sizediff+int(raidhosts[diskA['host']]-2)
    return w
 ########### Mirror DiskB Failed diskA free policy: Useability ########
   elif 'mirror' in diskB['raid']:    # useable type not to mirror large disks
    print('spare4_10')
    if norm(diskA['size']) > norm(minB['size']):
     w=100002
     return w
   else:
    print('spare4_11')
    w+=sizediff+10*int(diskA['host'] in diskB['host'])
    return w
 ########### RAID DiskB Failed diskA free policy: Availability ########
  else:
   print('spare4_12')
 ########### Raidz and DiskB Failed diskA free policy: Availability #########
   if 'raidz1' in diskB['raid']:
    print('spare4_13')
    w=sizediff+10*int(raidhosts[diskA['host']]-1)
    return w
   elif 'raidz2' in diskB['raid']:
    print('spare4_14')
    w=sizediff+10*int(raidhosts[diskA['host']]-2)
    return w
   elif 'raidz3' in diskB['raid']:
    print('spare4_15')
    w=sizediff+10*int(raidhosts[diskA['host']]-3)
    return w
 ########### Mirror and DiskB Failed diskA free policy: Availability #########
   elif 'mirror' in diskB['raid']:
    print('spare4_16')
    w+=sizediff+10*int(raidhosts[diskA['host']] -1)
    return w
  
def selectthedisk(freedisks,raid,allraids,allhosts):
 global leader, leaderip, myhost, myhostip, etcdip
 weights=[]
 finalw=[]
 hostcounts=allhosts.copy()
 balancetype=get(etcdip, 'balancetype/'+raid['pool'])
 for disk in raid['disklist']:
  if 'ONLINE' in disk['status']:
   if disk['host'] in hostcounts.keys():
    hostcounts[disk['host']]+=1
   else:
    hostcounts[disk['host']]=1
 if 'stripe' not in raid['name'] and 'ONLINE' in raid['status']:
  for diskA in raid['disklist']:
   for diskB in raid['disklist']:
    if diskA['actualdisk'] not in diskB['actualdisk']:
     w=getbalance(diskA.copy(),diskB.copy(),balancetype,hostcounts.copy(),raid['disklist'].copy())
     finalw.append({'newd':diskA,'oldd':diskB,'w':w})
  for diskA in freedisks:
   for diskB in raid['disklist']:
    if diskA['actualdisk'] not in diskB['actualdisk']:
     w=getbalance(diskA,diskB,balancetype,hostcounts,raid['disklist'])
     finalw.append({'newd':diskA,'oldd':diskB,'w':w})
 elif 'stripe' in raid['name']:
  for diskA in freedisks:
   for diskB in raid['disklist']: 
    w=getbalance(diskA,diskB,balancetype,hostcounts)
    finalw.append({'newd':diskA,'oldd':diskB,'w':w})
 elif 'DEGRAD' in raid['status']:
  defdisks=[x for x in raid['disklist'] if 'ONLINE' not in x['status']]
  onlinedisks=[x for x in raid['disklist'] if 'ONLINE' in x['status']]
  for diskA in freedisks:
   for diskB in defdisks:
    #####################################################
    #I need to check why we are comparing a faulty disk instead of the others
    ######################################################
    w=getbalance(diskA,diskB,balancetype,hostcounts,onlinedisks)
    finalw.append({'newd':diskA,'oldd':diskB,'w':w})
 finalw=sorted(finalw,key=lambda x:x['w'])
 print('finalw',finalw[0])
 return finalw[0] 

 
def solvestriperaids(striperaids,freedisks,allraids):
 global leader, leaderip, myhost, myhostip, etcdip
 global usedfree
 sparefit={}
 for raid in striperaids:
  sparelist=selectthedisk(freedisks,raid,allraids,{})
  if len(sparelist) > 0:
   try:
    sparefit[sparelist['newd']['actualdisk']].append(sparelist)
   except:
    sparefit[sparelist['newd']['actualdisk']]=[]
    sparefit[sparelist['newd']['actualdisk']].append(sparelist)
 for k in sparefit:
  sparefit[k]=sorted(sparefit[k],key=lambda x:x['w'])
 for k in sparefit:
  oldd=sparefit[k][0]['oldd'] 
  newd=sparefit[k][0]['newd'] 
  olddpool=sparefit[k][0]['oldd']['pool'] 
 cmdline=['/sbin/zpool', 'attach','-f', olddpool]
 ret=mustattach(cmdline,newd,oldd)
 if 'fault' not in ret:
  usedfree.append(ret)
 return
 
# QSD5.352 r10f (QC proof 10e D17): a mirror leg on another node's disk goes REMOVED (or UNAVAIL) when that node stops, and
# it stayed so after the node came back: the pool stays imported on the surviving owner the whole time, nothing reopens the
# leg (no zed / udev event reaches the node container), and the stand-in path below needs a device-mapper placeholder,
# which the container cannot make ("zpool replace ... /dev/": the placeholder name was empty, every pass).  Four
# stop/return cycles of zfs2 left pdhcp2401216152 DEGRADED.  Container flavour: when the leg's own disk is back (the
# by-id link exists and its SCSI device state is 'running', read from sysfs: the device itself is not opened here) the
# owner puts it back with 'zpool online' (ZFS resilvers what changed meanwhile).  At most one try per leg every 2 min;
# every try is logged in /root/reonline.log.  The physical flavour keeps its path (zed, the stand-in, the optimizer).
import re
# r10g (validator 10f V7): only a leg whose disk was really gone (REMOVED / UNAVAIL) is put back.  A FAULTED leg (real I/O
# errors on a disk that stays listed and 'running') is left to the operator: an online every 2 min made a failing disk
# flap in and out of the mirror.  After the online, FAULTED still counts as 'not in use'.
LEGDEAD = ('REMOVED', 'UNAVAIL')
LEGNOTINUSE = ('REMOVED', 'UNAVAIL', 'FAULT', 'OFFLINE')
REONLINELOG = '/root/reonline.log'
REONLINELAST = '/root/reonline.last'
REONLINEWAIT = 120
BYID = '/dev/disk/by-id/'
SYSBLOCK = '/sys/block/'

def reonlinelog(msg):
 try:
  from datetime import datetime
  with open(REONLINELOG, 'a') as f:
   f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' '+str(myhost)+' '+msg+'\n')
 except Exception:
  pass

def iscontainer():
 return os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10')

def devicerunning(name):
 path = BYID+name
 if not os.path.exists(path):
  return False
 dev = os.path.basename(os.path.realpath(path))
 base = re.sub(r'[0-9]+$', '', dev) if dev.startswith('sd') else dev
 try:
  with open(SYSBLOCK+base+'/device/state') as f:
   return f.read().strip() == 'running'
 except OSError:
  return False

def legstate(pool, name):
 try:
  out = subprocess.run(['timeout','30','/sbin/zpool','status',pool],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode('utf-8','replace')
 except Exception:
  return ''
 for line in out.split('\n'):
  w = line.split()
  if len(w) >= 2 and w[0] == name:
   return w[1]
 return ''

def reonlineleg(raid, disk):
 # True when the leg is in use again (online, resilvering): nothing else to do for it in this pass
 if not iscontainer():
  return False
 name = str(disk.get('name',''))
 status = str(disk.get('status',''))
 if 'scsi' not in name or not any(x in status for x in LEGDEAD):
  return False
 if str(disk.get('host','_1')) in ('_1', 'UNAVAIL', '', 'None'):
  return False            # lsscsi does not list the disk: its node is not back
 if not devicerunning(name):
  return False
 last = {}
 try:
  with open(REONLINELAST) as f:
   for line in f:
    k, tab, v = line.strip().partition(' ')
    if tab:
     last[k] = float(v)
 except Exception:
  pass
 key = str(raid.get('pool',''))+'/'+name
 if stamp() - last.get(key, 0) < REONLINEWAIT:
  return False
 last[key] = stamp()
 try:
  with open(REONLINELAST, 'w') as f:
   for k, v in last.items():
    f.write(k+' '+str(v)+'\n')
 except Exception:
  pass
 res = subprocess.run(['timeout','60','/sbin/zpool','online',raid['pool'],name],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 now = legstate(raid['pool'], name)
 ok = res.returncode == 0 and now != '' and not any(x in now for x in LEGNOTINUSE)
 reonlinelog(raid['pool']+' leg '+name+' was '+status+', its disk is back (host '+str(disk.get('host'))+'): zpool online rc '+str(res.returncode)
             +', now '+(now or '?')+('' if ok else ' -- not in use, retried in '+str(REONLINEWAIT)+' s: '+res.stderr.decode('utf-8','replace').strip()[:200]))
 return ok

# QSD5.352 r10h (QC proof 10g finding 7): the leader's optimizer took disks that only LOOK free.  The free list is every
# LIO disk that no ready node reports in one of its pools, so it also held (1) the legs of a pool that waits to be imported
# (exported by the stopping owner, not imported yet by the next host: P1's last zfs2 leg went to a sink pool 45 s after
# the export, then its zfs1 leg 46 s after zfs1's disks came back: P1 lost), (2) the disk of a REMOVED / UNAVAIL leg of an
# imported pool that has just come back (zpool status names that leg by its guid, "was /dev/disk/by-id/scsi-..."), and
# (3) a disk that was replaced out of a pool as FAULTED / OFFLINE seconds before (it went into a healthy pool 24 s later).
# 'zpool replace -f' then overrode ZFS's "is part of exported pool" refusal.  Container flavour (the physical flavour
# keeps its path): a free disk is RESERVED -- not offered to the optimizer, and not replaced in by the owner -- when
#   inpool      its id is named in 'zpool status' (any pool this kernel has imported, also as "was ..." of a lost leg);
#   pending     it is a member, in 'zpool import', of a pool this cluster knows (ActPool/ or poolnxt/) that is not imported;
#   quarantine  it left a pool as FAULTED / OFFLINE less than SPAREQUARANTINE ago (leader key sparequarantine/<disk>,
#               '<stamp>/<pool>/<state>'; deleting the key frees the disk at once);
#   grace       (leader only) it has been free for less than SPAREGRACE: a disk that just came back, or just left a pool,
#               waits until the imports and re-onlines of that moment are done (a new leader starts every disk's grace).
# And while any pool of the cluster is not ONLINE (degraded), the healthy raids are not re-balanced: free disks are kept
# for the healing.  Every change of the reserved set is logged in /root/sparereserve.log (/root/sparereserve.now = now).
SPAREGRACE = 180
SPAREQUARANTINE = 86400
SPAREGRACEF = '/root/sparegrace.last'
SPARERESERVELOG = '/root/sparereserve.log'
SPARERESERVENOW = '/root/sparereserve.now'
QUARANTINEKEY = 'sparequarantine/'
SCSIRE = re.compile(r'scsi-[0-9A-Za-z]+')
SDRE = re.compile(r'\b(sd[a-z]+)[0-9]*\b')

def zout(args, t=60):
 try:
  return subprocess.run(['timeout', str(t)]+args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode('utf-8', 'replace')
 except Exception:
  return ''

def poolsections(text):
 # {pool: its part of a 'zpool status' / 'zpool import' listing}
 secs = {}
 name = None
 for line in text.split('\n'):
  w = line.split()
  if len(w) >= 2 and w[0] == 'pool:':
   name = w[1]
   secs[name] = ''
  elif name is not None:
   secs[name] += line+'\n'
 return secs

def namedin(disk, text):
 ids = set(m.group(0) for m in SCSIRE.finditer(text))
 sds = set(m.group(1) for m in SDRE.finditer(text))
 return str(disk.get('name', '')) in ids or str(disk.get('actualdisk', '')) in ids or str(disk.get('devname', '-')) in sds

def pendingpools(allinfo):
 known = set()
 for pfx in ('ActPool/', 'poolnxt/'):
  for row in get(leaderip, pfx, '--prefix'):
   if isinstance(row, (list, tuple)) and len(row) > 1 and str(row[0]).startswith(pfx):
    known.add(str(row[0])[len(pfx):])
 imported = set(zout(['/sbin/zpool', 'list', '-H', '-o', 'name'], 30).split()) | set(allinfo.get('pools', {}).keys())
 return set(p for p in known if p and p not in imported)

def quarantined(now):
 res = {}
 for row in get(leaderip, QUARANTINEKEY, '--prefix'):
  if not (isinstance(row, (list, tuple)) and len(row) > 1 and str(row[0]).startswith(QUARANTINEKEY)):
   continue
  try:
   since = float(str(row[1]).split('/')[0])
  except ValueError:
   since = now            # unreadable stamp: counts from now (kept until the admin deletes the key)
  if now - since < SPAREQUARANTINE:
   res[str(row[0])[len(QUARANTINEKEY):]] = str(row[1])
 return res

def gracewait(freenames, now):
 first = {}
 try:
  with open(SPAREGRACEF) as f:
   for line in f:
    k, sp, v = line.strip().partition(' ')
    if sp:
     first[k] = float(v)
 except Exception:
  pass
 keep = dict((n, first.get(n, now)) for n in freenames)
 try:
  tmp = SPAREGRACEF+'.'+str(os.getpid())
  with open(tmp, 'w') as f:
   for k, v in keep.items():
    f.write(k+' '+str(v)+'\n')
  os.replace(tmp, SPAREGRACEF)
 except Exception:
  pass
 return dict((n, int(now-keep[n])) for n in freenames if now - keep[n] < SPAREGRACE)

def sparereserved(allinfo, disks, grace=True):
 # disks: {name: disk dict} of free disks; returns {name: reason} of those that must not be used now
 if not iscontainer():
  return {}
 now = stamp()
 if not disks:
  if grace:
   gracewait([], now)       # no free disk now: a disk free again later starts a new grace
  return {}
 why = {}
 status = poolsections(zout(['/sbin/zpool', 'status'], 60))
 for name, d in disks.items():
  for pool, sec in status.items():
   if namedin(d, sec):
    why[name] = 'inpool '+pool
    break
 pending = pendingpools(allinfo)
 if pending:
  scan = poolsections(zout(['/sbin/zpool', 'import'], 90))
  for name, d in disks.items():
   if name in why:
    continue
   for pool, sec in scan.items():
    if pool in pending and namedin(d, sec):
     why[name] = 'pending '+pool
     break
 quar = quarantined(now)
 for name in disks:
  if name not in why and name in quar:
   why[name] = 'quarantine '+quar[name]
 if grace:
  for name, age in gracewait(list(disks.keys()), now).items():
   if name not in why:
    why[name] = 'grace free for '+str(age)+' s < '+str(SPAREGRACE)+' s'
 reservelog(why)
 return why

def reservelog(why):
 kinds = '\n'.join(sorted(k+' '+v.split(' free for ')[0] for k, v in why.items()))
 try:
  old = open(SPARERESERVENOW).read()
 except Exception:
  old = None
 if old == kinds:
  return
 try:
  with open(SPARERESERVENOW, 'w') as f:
   f.write(kinds)
  reonlinelog_to(SPARERESERVELOG, 'reserved now: '+('; '.join(k+' ('+v+')' for k, v in sorted(why.items())) or 'none'))
 except Exception:
  pass

def reonlinelog_to(path, msg):
 try:
  from datetime import datetime
  with open(path, 'a') as f:
   f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' '+str(myhost)+' '+msg+'\n')
 except Exception:
  pass

def quarantineleg(pool, name, state):
 # the owner replaced a FAULTED / OFFLINE leg out of <pool>: its disk must not go into a pool again right away
 if not iscontainer() or not str(name).startswith('scsi-'):
  return
 if not any(x in str(state) for x in ('FAULT', 'OFFLINE')):
  return
 put(leaderip, QUARANTINEKEY+name, str(stamp())+'/'+str(pool)+'/'+str(state))
 reonlinelog_to(SPARERESERVELOG, 'quarantine '+name+': replaced out of '+str(pool)+' as '+str(state)+' (free again after '+str(SPAREQUARANTINE)+' s or when the key '+QUARANTINEKEY+name+' is deleted)')

def degradedpools(allinfo):
 res = set()
 for rname, raid in allinfo.get('raids', {}).items():
  if 'free' in str(raid.get('name', '')) or raid.get('pool') in ('pree', None):
   continue
  if 'ONLINE' not in str(raid.get('status', '')):
   res.add(str(raid.get('pool')))
 return res

def solvedegradedraid(raid,diskname):
 global leader, leaderip, myhost, myhostip, etcdip
 if 'dm-' in str(diskname):
    return
 print('diskname', diskname)
 if 'replacing' in diskname:
    return
 hosts=get(etcdip, 'ready','--prefix')
 hosts=[host[0].split('/')[1] for host in hosts]
 raidhosts= set()
 defdisk = [] 
 disksample = []
 sparedisk = []
 if 'stripe' in raid['name']:
    #cmdline2=['/sbin/zpool', 'detach',raid['pool'], disk['actualdisk']]
    cmdline2=['/sbin/zpool', 'detach',raid['pool'], diskname ]
    forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print('detaching the faulty disk',forget.stderr.decode())
    return
 defdisk.append(diskname)
 dmcmd=['zpool', 'status']
 dminuse = subprocess.run(dmcmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().split()
 dmcmd=['zpool','import']
 dminuse = dminuse + subprocess.run(dmcmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().split()
 dminuse = [ 'dm-'+x.split('dm-')[1].split(' ')[0] for x in dminuse  if 'dm-' in x ] + [ 'dm-1', 'dm-0' ]
 dmcmd = '/pace/lstdm.sh'
 dmstuplst = subprocess.run(dmcmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().split()
 dmstup = '0'
 for dm in dmstuplst:
    if dm not in str(dminuse) or 'was /dev/'+dm in (dminuse):
     dmstup = dm
 if dmstup == '0':
    cmddm= ['/pace/mkdm.sh']
    dmstup = subprocess.run(cmddm,stdout=subprocess.PIPE).stdout.decode().split('result_')[1]
 # r10f (D17): no placeholder could be made (the container flavour has no device-mapper target): 'zpool replace ... /dev/'
 # only failed every pass ("must be a block device"); the leg is left for reonlineleg() when its disk comes back
 if not str(dmstup).strip():
    print('no stand-in placeholder for the lost disk, mirror left degraded until its disk is back', raid['pool'], diskname)
    return
 diskuid = diskname
 if 'scsi' in diskname:
    # the node image of the container flavour has no zdb: then the guid of the faulty disk is not looked up and the
    # disk is given to 'zpool replace' by its name (it is still listed by zpool status when it is FAULTED), instead of
    # the whole selectspare run dying with FileNotFoundError every cycle
    try:
     cmdline2='/sbin/zdb -e -C '+raid['pool']
     forget=subprocess.run(cmdline2.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE)
     if forget.returncode:
      cmdline2='/sbin/zdb -C '+raid['pool']
      forget=subprocess.run(cmdline2.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE)
     forget=forget.stdout.decode().replace(' ','').split('\n')
    except FileNotFoundError:
     forget=[]
    faultdisk = [ x for x in forget if 'guid' in x or (diskname in x and 'path' in x) ]
    eindex = 0 
    for fa in faultdisk:
     if diskname in fa:
      eindex = faultdisk.index(fa)
      break
    print('faultdisk',faultdisk, diskname)
    diskuid = diskname
    if len(faultdisk) > 0:
        diskuid = faultdisk[eindex-1].split(':')[1]
    
    
 cmdline2=['/sbin/zpool', 'replace','-f',raid['pool'], diskuid,'/dev/'+dmstup]
 forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
 if forget.returncode != 0:
    # QSD5.345: the lost leg is detached only after the stand-in placeholder took its place. A failed replace (device
    # busy, placeholder too small, pool gone) used to be followed by the offline of the placeholder and the detach of
    # the lost leg anyway: the mirror lost its redundancy and became a plain stripe (test 681). Now: log and leave the
    # mirror degraded; the next pass (or the return of the node) heals it.
    print('replace of the lost disk failed, mirror left degraded (no offline/detach)', raid['pool'], diskuid,
          '/dev/'+dmstup, 'rc', forget.returncode, forget.stderr.decode())
    with open('/root/dmproblem','w') as f:
       f.write('cmdline '+ " ".join(cmdline2)+'\n')
       f.write('returncode: '+str(forget.returncode)+'\n')
       f.write('result: '+forget.stdout.decode()+'\n')
       f.write('result: '+forget.stderr.decode()+'\n')
       f.write('skipped: offline /dev/'+dmstup+' and detach '+str(diskuid)+'\n')
    return
 sleep(2)
 cmdline2=['/sbin/zpool', 'offline',raid['pool'],'/dev/'+dmstup]
 forget2=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
 sleep(2)
 cmdline2=['/sbin/zpool', 'detach',raid['pool'],diskuid]
 forget2=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
 sleep(2)

 with open('/root/dmproblem','w') as f:
    f.write('cmdline '+ " ".join(cmdline2)+'\n')
    f.write('result: '+forget2.stdout.decode()+'\n')
    f.write('result: '+forget2.stderr.decode()+'\n')
    f.write('dmstuplst[0]: '+str(dmstuplst)+'\n')
 print('forgetting the dead disk result by internal dm stup',forget.stderr.decode())
 print('returncode',forget.returncode,dmstuplst)
 # QSD5.345: the bookkeeping that followed here used dmstuplst[0][0] as an etcd key, i.e. the FIRST LETTER of the first
 # device-mapper name ('d'): a failed replace deleted every key of the leader etcd that starts with 'd' (dirty/..., dns...)
 # and a good one wrote a key 'd' that nothing reads.  Removed; the placeholder is found again by lstdm.sh (unused
 # placeholders only).
 return

def solvetheasks(needtoreplace):
    global leader, leaderip, myhost, myhostip, etcdip
    theasks = get(leaderip, 'ask/needtoreplace', '--prefix')
    for askleft,askright in theasks:
        freedisk = askright.split('/')[-2] 
        if freedisk in str(needtoreplace) and askleft.replace('ask/','') in str(needtoreplace):    ### ignore
            continue
        elif freedisk in str(needtoreplace) and askleft.replace('ask/','') not in str(needtoreplace): ### reject
            dels(leaderip, askleft)
        elif freedisk not in str(needtoreplace):    ##### accept
            put(leaderip, askleft.replace('ask/',''), askright)
   
    return
  
def spare2(*args):
 global newop
 global usedfree 
 global leader, leaderip, myhost, myhostip, etcdip
 if args[0]=='init':
        leader = args[1]
        leaderip = args[2]
        myhost = args[3]
        myhostip = args[4]
        etcdip = args[5]
        initqueue(leaderip, myhost) 
        #getall('init',leader, leaderip, myhost, myhostip, etcdip)
        return
 
 initputzpool(leader, leaderip, myhost, myhostip)
 putzpool()
 alloptimized = 'yes'
 needtoreplace = get(leaderip, 'needtoreplace', '--prefix') 
 if len(needtoreplace) > 0:
      alloptimized = 'no'
 if myhost == leader:
    solvetheasks(needtoreplace)
 needtoreplace = get(leaderip, 'needtoreplace', '--prefix') 
 myneedtoreplace = [x for x in needtoreplace if myhost in str(x) ] 
 exception = get(etcdip,'offlinethis','--prefix')
 print('it is needtoreplace',needtoreplace)
 for raidinfo in myneedtoreplace:
      alloptimized = 'no'
      allinfo = getall(leaderip) 
      print('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
      print('need to replace',raidinfo)
      poolname = raidinfo[0].split('/')[2]
      #if poolname in str(exception):
      # print('this pool should not be automatically healed ')
      # continue
      dmcmd = 'zpool status '+poolname
      chkstatus = subprocess.run(dmcmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode('utf-8')
      if 'resilvering' in chkstatus:
       print('this pool is in resilvering status, we should wait till it completes the resilving')
       continue
      print('hhhhhhhhhhhhhhhhhhhhhhi iam here')
      raidname = raidinfo[0].split('/')[-1]
      rmdiskname = raidinfo[1].split('/')[0]
      adiskname = raidinfo[1].split('/')[1]
      rmorig = rmdiskname
      rmstate = str(allinfo['disks'].get(rmorig, {}).get('status', ''))
      # r10h (finding 7): the request was made by the leader some seconds ago; a disk that is reserved NOW (a member of a
      # pool waiting to import, of an imported pool, or quarantined) is not replaced in: 'zpool replace -f' would override
      # ZFS's own "part of exported pool" refusal.  The request is dropped; the leader's next pass decides again.
      held = sparereserved(allinfo, {adiskname: allinfo['disks'].get(adiskname, {'name': adiskname})}, grace=False)
      if adiskname in held:
         reonlinelog_to(SPARERESERVELOG, 'replace request '+poolname+' '+rmorig+' -> '+adiskname+' dropped: '+held[adiskname])
         dels(leaderip,'ask/needtoreplace',adiskname)
         dels(leaderip,'needtoreplace',adiskname)
         continue
      print('rmdisk:',rmdiskname)
      print('raidname:',raidname)
      print('adiskname:',adiskname)
      if 'mirror-temp' in raidname:
         cmdline2=['/sbin/zpool', 'attach','-f', poolname, rmdiskname,adiskname]
      elif '_1' in rmdiskname:
         print(' the remove disk is not identified') 
         continue
      else:
        print('hhhhhhhhhhhhhhhhhhhhhhhrmdisk', rmdiskname)
        try:
            rmdiskname = allinfo['disks'][rmdiskname]['actualdisk']
        except:
            print('rmdisk',rmdiskname,'is not available, so starting over')
            dels(leaderip,'ask/needtoreplace',adiskname)
            dels(leaderip,'needtoreplace',adiskname)
            continue
            
        print('the rmdisk is healthy', rmdiskname)
        #cmdline2=['/sbin/zpool', 'status',poolname]
        #cpoolinfo=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()
        #cmdline2= 'dd if=/dev/zero of=/dev/disk/by-id/'+adiskname+' count=100 bs=1M status=progress'
        #writing=subprocess.run(cmdline2.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()
        #if rmdiskname in cpoolinfo:
        print('will do:', poolname, raidname, rmdiskname, adiskname)
        cmdline2=['/sbin/zpool', 'replace','-f',poolname, rmdiskname,adiskname]
        print(cmdline2)
      forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      print('forget',forget.returncode)
      print('cmdline2'," ".join(cmdline2))
      print('theresult',forget.stdout.decode())
      print('return code',forget.returncode)
      if forget.returncode == 0:
         quarantineleg(poolname, rmorig, rmstate)      # r10h (finding 7)
      #if forget.returncode == 0:
      #  dels(leaderip,'offline',poolname)
      dels(leaderip,'ask/needtoreplace',adiskname)
      dels(leaderip,'needtoreplace',adiskname)
      #cmd = ['systemctl', 'restart', 'zfs-zed']
      #subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      #dels(leaderip,'ask/needtoreplace',raidname)
      #dels(leaderip,'needtoreplace',raidname)
      #dosync('sync/needtoreplace/____/request','needtoreplace_'+str(stamp()))
      return
 freedisks=[]
 allraids=[]
 freeraids=[]
 hosts=get(etcdip, 'ready','--prefix')
 allhosts=set()
 allinfo = getall(leaderip) 
 alldisks = {}
 excludeddisks = ''
 for pool in allinfo['pools']:
    if 'ree' in pool:
        continue
    if allinfo['pools'][pool]['host'] not in myhost:
        continue
    if allinfo['pools'][pool]['changeop'] in ['ONLINE']:
        continue
    for raid in allinfo['pools'][pool]['raids']:
        print('raid:',pool)
        if allinfo['raids'][raid]['changeop'] in ['ONLINE']:
            continue
        for disk in allinfo['raids'][raid]['disklist']:
            if disk['changeop'] not in ['free','ONLINE']:
                print('iamhere',disk['name'])
                excludeddisks = excludeddisks+','+disk['name']
                if 'dm-' in disk['name']:
                    disk['host'] = myhost
                    continue
                alloptimized = 'no'
                if reonlineleg(allinfo['raids'][raid], disk):
                    continue       # r10f (D17): the leg's own disk is back and in use again
                solvedegradedraid(allinfo['raids'][raid],disk['name'])
 if myhost != leader:
    return 
 actives = str(get(leaderip, 'ready','--prefix'))
 for need in needtoreplace:
    needhost=need[0].split('/')[1]
    if needhost not in actives:
        dels(leaderip, need[0],need[1])
 needtoreplace = str(get(leaderip, 'needtoreplace', '--prefix') )+str(get(leaderip,'offline','--prefix'))
 for diskname in allinfo['disks']:
    disk = allinfo['disks'][diskname]
    if disk['changeop'] in ['free']:
       alldisks[disk['name']] = disk.copy()
 # r10h (finding 7): disks that only look free are not offered (container flavour; see sparereserved)
 for name in sparereserved(allinfo, alldisks):
    alldisks.pop(name, None)
 degraded = degradedpools(allinfo) if iscontainer() else set()
 for raidname in allinfo['raids']:
    raid = allinfo['raids'][raidname]
    if degraded and 'ONLINE' in str(raid.get('status', '')):
        print('re-balance held, pools not ONLINE:', degraded, raidname)
        continue
    # QSD5.345: the free list AND the spare-cache list (raid 'cache' of the pseudo pool 'pree', putzpool.py) are not raids of
    # a pool: nothing to optimize there.  The cache list was not skipped, solvefaultyreplace() raised KeyError
    # 'replacingroup' on its disk and the exception ended every selectspare pass of the leader, so with one disk on the
    # spare-cache list no pool was healed any more (QC test 712: DEGRADED mirror, hot-added disk never used).
    if 'free' not in raid['name'] and raid.get('pool') != 'pree' and raid['silvering'] == 'no':
        diskset = set(raid['disks'])
        faultyreplaceflag = 0
        faultyreplaceflag = solvefaultyreplace(raid)
        if faultyreplaceflag > 0:
            continue
        diskwindow = alldisks.copy()
        for disk in raid['disklist']:
            if 'dm-' not in disk['name'] and disk['changeop'] in ['ONLINE']:
                diskwindow[disk['name']] = disk
        print('##################################################')
        print('optimizing raid:',raid['name'])
        print('its disks:',[x['name'] for x in raid['disklist']])
        print('exclude lst:',needtoreplace)
        bestdisks = optimizedisks(leaderip, raid, diskwindow, needtoreplace)
        toreplace = ''
        toplace = ''
        bestdiskset = set(bestdisks.split(','))
        toplace = bestdiskset - diskset
        toreplace = diskset - bestdiskset
        print('toreplace', toreplace)
        print('toplace', toplace)
        if diskset == bestdiskset or len(','.join(list(toplace))) == 0 :
            print('already optimized')
            continue 
        else:
                alloptimized = 'no'
                needtoreplace = needtoreplace+','+','.join(list(toplace))
                print('new arrangement')
                print('sssssssssssssssssssssssssssssss')
                print('bestdisk set',bestdiskset)
                print('old disk set',diskset)
                print('to replace',toreplace)
                print ('to place',  toplace)
                print(raid['disklist'][0]['name'])
                print('raidname:',raid['name'])
                print('sssssssssssssssssssssssssssssss')
                pool = raid['pool']
                host = raid['host']
                raidname = raid['name']
                if 'mirror-temp' in raidname:
                    toreplace = set()
                    toreplace.add(raid['disklist'][0]['name'])
                 #break
                for x in zip(list(toreplace),list(toplace)):
                    print(leaderip, 'needtoreplace/'+host+'/'+pool+'/'+raidname,x[0]+'/'+x[1])
                    put(leaderip, 'needtoreplace/'+host+'/'+pool+'/'+raidname,x[0]+'/'+x[1])
 
 if alloptimized == 'no':
    print('still not all are optimized in this node')
 else:
    print('all is optimized in this node')
    if len(exception) > 0 :
        dels(leaderip,'offline','--prefix') 
        stampit = str(stamp())
        dosync('sync/offlinethis/add/request','offlinethis_'+stampit)
        
 usedfree = []
 print('_alloptimized',alloptimized)
 return
 
 
 
if __name__=='__main__':
  leaderip = sys.argv[1]
  myhost = sys.argv[2]
  leader=get(leaderip, 'leader')[0]
  myhostip=get(leaderip,'ready/'+myhost)[0] 
  if myhost == leader:
   etcdip = leaderip
  else:
   etcdip = myhostip
  #getall('init',leader, leaderip, myhost, myhostip, etcdip)
  spare2(sys.argv[1:])
