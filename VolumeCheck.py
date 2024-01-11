#!/usr/bin/python3
import subprocess,sys, os
from etcdgetpy import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
#from broadcasttolocal import broadcasttolocal 
from time import time as stamp
from glob import glob


#leader=get('leader','--prefix')[0][0].split('/')[1]

def dosync(*args):
  global leaderip, leader
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 

def getippos(vtype):
    if ('cifs' or 'home') in vtype:
        return 7
    elif 'nfs' in vtype:
        return 9
    else: 
        return 0
def getdirtyvols(vtype, etcds, replis, dockers):
    global leader, leaderip, myhost, myhostip, etcdip
    cmdline = '/TopStor/getvols.sh '+vtype
    result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
    result = [x for x in result if 'pdhc' in x]
    resultdisabled = [ x for x in result if 'disable' in str(x) ]
    resultactive = [ x for x in result if 'active' in str(x) ]
    etcddisabled= [ x for x in etcds if 'disable' in str(x) ]
    etcdactive= [ x for x in etcds if 'active' in str(x) ]
    dirtyset = set()
    ipset = set()
    print('###############3')
    for res in result:
        reslist=res.split('/')
        ippos = getippos(vtype)
        if reslist[-1] == 'active':
            if reslist[1] in str(etcddisabled):
                dirtyset.add(res)
        else:
            if reslist[1] in str(etcdactive):
                dirtyset.add(res)
                print('here2', res)
        if reslist[1] not in str(etcds):
            dirtyset.add(res)
        for dckr in dockers.split('\n'):
            if reslist[ippos] in dckr and reslist[-1] =='active':
                dckrname=dckr.split(' ')[-1]
                cmdline = 'docker inspect '+dckrname
                result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
                print(dckrname, reslist[1],reslist)
                if reslist[1] not in str(result):
                    print('not in')
                    dirtyset.add(res)
        if reslist[ippos] not in str(dockers) and 'active' in reslist[-1]:
            dirtyset.add(res)
    return dirtyset

def nfsold( etcds, replis, exports):
    global leader, leaderip, myhost, myhostip, etcdip
    #dirtyset = getdirtyvols('nfs', etcds, replis, )
    flag = 0
    for export in exports:
        with open(export) as f:
            pool = export.split('/')[1]
            vol = export.split('.')[1]
            print(pool,vol)
            exportetctip = 0
            for line in f:
                if len(line) < 5:
                    continue
                print('theline',line)
                if 'SUMMARY' in line:
                    exportetc = line.split(' ')[3]
                    exportetcip = exportetc.split('/')[-3]
                    exportetcsub = exportetc.split('/')[-2]
                    exportetcactive = exportetc.split('/')[-1]
                    if exportetc[2:-2] not in str(etcds):
                        dels(leaderip, 'volumes', vol)
                        put(leaderip,'volumes/NFS/'+myhost+'/'+pool+'/'+vol,exportetc)
                        flag = 1
                else:
                    if 'active' in exportetcactive: 
                        with open('/TopStordata/exportip.'+vol+'_'+exportetcip, 'w') as fip:
                            fip.write(line)
                        cmdline = '/TopStor/nfs.sh '+exportetcip+' '+exportetcsub
                        subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
                    else:
                        cmdline = '/TopStor/nfsumount.sh '+vol
                        subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
    if flag:
        dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
        
    return    
def nfs( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('nfs', etcds, replis, dockers)
 print('dirty',dirtyset)
 for res in dirtyset:
   reslist=res.split('/')
#pdhcp1287810983/nftt_2386812076/10.11.11.*/rw/sync/insecure/no_root_squash/no_all_squash/Everyone/10.11.11.23/24/active
#pdhcp1287810983/forsnap_2050719952/no/yes/Everyone/administrator/yes/10.11.11.8/24/active
   print('update',reslist[1])
   cmdline = '/TopStor/undockerthis.sh '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   left='volumes/NFS/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   #broadcasttolocal(left,res)
   cmdline='/TopStor/nfs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[9]+' '+reslist[10]+' NFS '+' '.join(reslist[11:])
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print(result)
   put(etcdip,'dirty/volume','0')






def cifs( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('cifs', etcds, replis, dockers)
 print('dirty',dirtyset)
 for res in dirtyset:
   reslist=res.split('/')
   print('update',reslist[1])
   cmdline = '/TopStor/undockerthis.sh '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   if 'DOMAIN' in str(res):
    left='volumes/CIFS_'+reslist[9]+'/'+myhost+'/'+'/'.join(reslist[0:2])
   else:
    left='volumes/CIFS/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   #broadcasttolocal(left,res)
   if 'DOMAIN' in str(res):
     #cmdline='/TopStor/cifsmember.sh '+leaderip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' cifs '+' '.join(reslist[9:])
     cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS_'+reslist[9]+' '+' '.join(reslist[9:])
     print('cmdline',cmdline)

     #cmdline='/TopStor/VolumeActivateCIFSdom '+leaderip+' vol='+reslist[1]+' user=system'
   else:
     cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS '+' '.join(reslist[9:])
    #cmdline='/TopStor/VolumeActivateCIFS '+leaderip+' vol='+reslist[1]+' user=system'
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print(result)
   put(etcdip,'dirty/volume','0')

def homes(etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('home', etcds, replis, dockers)
 print('dirty',dirtyset)
 for res in dirtyset:
   reslist=res.split('/')
   print('update',reslist[1])
   cmdline = '/TopStor/undockerthis.sh '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   left='volumes/HOMEE/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   #broadcasttolocal(left,res)
   cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' HOMEE '+' '.join(reslist[9:])
    #cmdline='/TopStor/VolumeActivateCIFS '+leaderip+' vol='+reslist[1]+' user=system'
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print(result)
   put(etcdip,'dirty/volume','0')


def iscsi(etcds, replis):
 global leader, leaderip, myhost, myhostip, etcdip
 cmdline = 'targetcli ls '
 targets = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 cmdline = '/TopStor/getvols.sh iscsi'
 result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
 result = [x for x in result if 'pdhc' in x]
 print('###############3')
 for res in result:
  reslist=res.split('/')
  print('reslist1',reslist[1])
  if reslist[1] not in str(etcds):
   left='volumes/ISCSI/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   #broadcasttolocal(left,res)
  if reslist[1] not in targets:
   print(reslist)
   cmdline='/TopStor/iscsi.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[2]+' '+reslist[3]+' ISCSI '+reslist[4]+' '+reslist[5]+' '+reslist[6]+' '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')


def volumecheck(etcds, replis, *args):
 global leader, leaderip, myhost, myhostip, etcdip
 if str(etcds)=='init':
     leader = replis 
     leaderip = args[0]
     myhost = args[1]
     myhostip = args[2]
     etcdip = args[3]
     return

 cmdline = 'docker ps'
 dockers = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 #cmdline = 'ls /TopStordata'
 #exports = subprocess.run(cmdline.split(),shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
 cmdline = 'rm -rf /TopStordata/exportip*'
 subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 exports = glob('/pdhc*/exports*')
 with open('/root/volumecheck','w') as f:
  f.write(str(etcds))
 #exports = [ x.split('exports.')[1] for x in exports ]
 cifs(etcds, replis, dockers)
 nfs(etcds, replis, dockers)
 homes(etcds, replis, dockers)
 iscsi(etcds, replis)
  
   
if __name__=='__main__':
  leaderip = sys.argv[1]
  myhost = sys.argv[2]
  leader=get(leaderip, 'leader')[0]
  myhostip=get(leaderip,'ready/'+myhost)[0] 
  if myhost == leader:
   etcdip = leaderip
  else:
   etcdip = myhostip
   
 
  etcds = get(etcdip, 'volumes','--prefix')
  replis = get(etcdip, 'replivol','--prefix')
  volumecheck(etcds, replis)
