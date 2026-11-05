#!/usr/bin/python3
import subprocess,sys, os
from etcdgetpy import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
#from broadcasttolocal import broadcasttolocal 
from time import time as stamp
from glob import glob
import json
from concurrent.futures import ThreadPoolExecutor

# QSD5.330: after a take-over every dirty volume is started in parallel.  Volumes that share an address are
# processed one after the other (cifs.py also takes a per-address lock); the volume types run side by side.
def runbygroup(items, keyf, worker):
    groups = {}
    for it in items:
        groups.setdefault(keyf(it), []).append(it)
    def rungroup(g):
        for it in g:
            try:
                worker(it)
            except Exception as e:
                print('volume worker failed', it, e)
    if not groups:
        return
    with ThreadPoolExecutor(max_workers=len(groups)) as ex:
        list(ex.map(rungroup, groups.values()))

_inspectcache = {}
def inspectall(dockers):
    # one docker inspect for all running containers (was one call per volume)
    global _inspectcache
    names = [l.split(' ')[-1] for l in dockers.split('\n')[1:] if l.strip()]
    _inspectcache = {}
    if not names:
        return
    out = subprocess.run(['docker','inspect']+names,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode('utf-8')
    try:
        for d in json.loads(out):
            _inspectcache[d['Name'].lstrip('/')] = json.dumps(d)
    except Exception:
        _inspectcache = {}

def inspectone(dckrname):
    if dckrname in _inspectcache:
        return _inspectcache[dckrname]
    cmdline = 'docker inspect '+dckrname
    return subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')


#leader=get('leader','--prefix')[0][0].split('/')[1]

def dosync(*args):
  global leaderip, leader
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 

def getippos(vtype):
    print('vtype',vtype)
    if vtype in ['cifs', 'home']:
        return 7
    elif 'nfs' in vtype:
        return 9
    else: 
        return 0
def registered(name, etcds):
    # QSD5.352 (QC 706): a volume counts as registered only when a key ends in /<name> and its value is a real record
    # (7 or more '/' fields).  The test was 'name in str(etcds)': a dummy key with the value _1 (old VolumeActivateHome) or
    # any other key or value that contains the name kept a lost record from ever being written again.
    for e in etcds:
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            continue
        if str(e[0]).split('/')[-1] == name and len(str(e[1]).split('/')) >= 7:
            return True
    return False

def sharesummary(pool, name):
    # the SUMMARY field of /<pool>/smb.<name> as getvols.sh prints it (pool/name/readv/brows/writev/admin/writea/ip/sub/
    # status), '' when the file or the line is missing
    try:
        with open('/'+pool+'/smb.'+name) as f:
            for i, line in enumerate(f):
                if i > 1:
                    break
                if 'SUMMARY' in line:
                    parts = line.split()
                    return parts[3] if len(parts) > 3 else ''
    except Exception:
        pass
    return ''

def current(res):
    # QSD5.352 r9 (prover D5, validator r8 R3): a dirty volume is acted on only while its share file still says what this
    # pass read.  getvols.sh runs before the per-address work; a home changed (VolumeChangeHOME), disabled or deleted in
    # between was handled with the OLD line: its old record was written back to the leader and cifs.py started the old
    # address again (HOMEE-<old ip> came back on a follower and held the dataset, the next delete failed with NFS1001).
    reslist = res.split('/')
    if len(reslist) < 2:
        return False
    return sharesummary(reslist[0], reslist[1]) == res

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
        if not registered(reslist[1], etcds):
            dirtyset.add(res)
        for dckr in dockers.split('\n'):
            dckrip = dckr.split(' ')[-1].split('-')[-1]
            if dckrip != reslist[ippos]:
                continue
            if reslist[ippos] in dckr and reslist[-1] =='active':
                dckrname=dckr.split(' ')[-1]
                result = inspectone(dckrname)
                print(dckrname, reslist[1],reslist)
                if reslist[1] not in str(result):
                    print('gggggggggggggggggggggggggggggggggggggggggg')
                    print('not in',ippos, reslist[ippos], dckrip)
                    print('reslist1',reslist[1], dckrname)
                    print('gggggggggggggggggggggggggggggggggggggggggg')
                    dirtyset.add(res)
        if reslist[ippos] not in dockers and 'active' in reslist[-1]:
            dirtyset.add(res)
    print('dirtyset', dirtyset)
    return dirtyset

def nfs( etcds, replis, exports):
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

def nfsnew( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('nfs', etcds, replis, dockers)
 print('cccccccccccccccccccccccccccccc')
 print('dirty',dirtyset)
 print('cccccccccccccccccccccccccccccc')
 def one(res):
   reslist=res.split('/')
   print('update',reslist[1])
   cmdline = '/TopStor/undockerthis.sh '+reslist[getippos('nfs')]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   left='volumes/NFS/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   cmdline='/TopStor/nfsnew.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[9]+' '+reslist[10]+' NFS'
   print('aloooooooooooooooooooooo')
   print(cmdline)
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   put(etcdip,'dirty/volume','0')
 runbygroup(sorted(dirtyset), lambda r: r.split('/')[getippos('nfs')], one)

def cifs( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('cifs', etcds, replis, dockers)
 print('cccccccccccccccccccccccccccccc')
 print('dirty',dirtyset)
 print('cccccccccccccccccccccccccccccc')
 def one(res):
   reslist=res.split('/')
   if not current(res):
     print('share file changed since this pass read it, left to the next pass', res)
     return
   print('update',reslist[1])
   cmdline = '/TopStor/undockerthis.sh '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   if 'DOMAIN' in str(res):
    left='volumes/CIFS_'+reslist[9]+'/'+myhost+'/'+'/'.join(reslist[0:2])
   else:
    left='volumes/CIFS/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   print('tosync this',leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   if 'DOMAIN' in str(res):
     cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+leaderip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS_'+reslist[9]+' '+' '.join(reslist[9:])

   else:
    cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+leaderip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS '+' '.join(reslist[9:])
    print('cif cifs: '+cmdline)
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print('cifs result',result)
   put(etcdip,'dirty/volume','0')
 runbygroup(sorted(dirtyset), lambda r: r.split('/')[7], one)

def homes(etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 print('----------------')
 dirtyset = getdirtyvols('home', etcds, replis, dockers)
 print('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh')
 print('dirty',dirtyset)
 print('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh')
 def one(res):
   reslist=res.split('/')
   if not current(res):
     print('share file changed since this pass read it, left to the next pass', res)
     return
   print('update',reslist[1])
   cmdline = '/TopStor/undockerthis.sh '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   left='volumes/HOMEE/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   # r9 (validator r8 R3): cifs.py reads the homes of the address and the user hashes from the LEADER (as VolumeChangeHOME
   # since r8); a follower's own copy lags the sync loop and served a disabled or moved home again
   cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+leaderip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' HOMEE '+' '.join(reslist[9:])
   print('home cifs: '+cmdline)
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print('result',result)
   put(etcdip,'dirty/volume','0')
 runbygroup(sorted(dirtyset), lambda r: r.split('/')[7], one)


def iscsi(etcds, replis):
 global leader, leaderip, myhost, myhostip, etcdip
 cmdline = 'targetcli ls '
 targets = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 cmdline = '/TopStor/getvols.sh iscsi'
 result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
 result = [x for x in result if 'pdhc' in x]
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

def _runto(cmd, timeout=10, out=True):
    # r9b (validator r9 V7): (returncode, stdout) or None when the command did not end in <timeout> s.  The child is killed
    # and NOT waited for (subprocess.run(timeout=) waits after the kill, and a zfs stuck in the kernel never ends).
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE if out else subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        o, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
        return None
    return p.returncode, (o or b'').decode('utf-8')

def homesweep(etcds, minage=30):
    # QSD5.352 r9 (prover D5, validator r8 R3): a HOMEE-<ip> container of this node that serves a home which is no longer
    # an ACTIVE home on <ip> (moved to another address, disabled, deleted) was never touched: VolumeCheck only starts what
    # is missing.  After an address change on a follower an old-address container started again stayed for good, kept the
    # old address on the node and the dataset busy (the home delete failed with NFS1001), and a disabled home stayed in a
    # shared container.  A container is checked by the datasets it mounts (/<pool>/<home>):
    #  - valid home: its share file says <ip> and 'active';
    #  - stale home: its share file says another address or another status, or file and dataset are both gone (deleted),
    #    AND the leader's record does not say '<ip> active' either (the file and the record agree);
    #  - anything else (pool not mounted, a dataset without its file): unknown, the container is left alone.
    # Stale homes and no valid one: the container and the address go (VolumeDockerChange.py; the address stays while another
    # dataset has it).  Stale and valid ones: cifs.py starts the address again from the leader's records (without the stale
    # homes).  Only containers older than <minage> s (one that is just being started or changed is left to its script).
    global leader, leaderip, myhost, myhostip
    import re, datetime
    # r9b (validator r9 V7): every docker / zfs call of the sweep has a timeout (a hung zfs on a suspended pool held the whole
    # VolumeCheck pass); a timeout = unknown, nothing is done
    r = _runto(['docker','ps','--format','{{.Names}}'])
    if r is None:
        print('home sweep: docker ps timed out')
        return []
    names = r[1].split()
    records = {}
    for e in etcds:
        if isinstance(e, (list, tuple)) and len(e) > 1:
            records[str(e[0]).split('/')[-1]] = str(e[1]).split('/')
    done = []
    for cname in names:
        if not cname.startswith('HOMEE-'):
            continue
        ip = cname[len('HOMEE-'):]
        try:
            info = json.loads(_runto(['docker','inspect',cname])[1])     # a timeout (None) = unknown: skipped
            info = info[0] if isinstance(info, list) else info
        except Exception:
            continue
        try:
            started = datetime.datetime.strptime(info['State']['StartedAt'][:19], '%Y-%m-%dT%H:%M:%S')
            age = (datetime.datetime.utcnow() - started).total_seconds()
        except Exception:
            continue
        if age < minage:
            continue
        homes = [ m.get('Source','') for m in info.get('Mounts', []) if re.match(r'^/pdhc[^/]*/[^/]+$', str(m.get('Source',''))) ]
        if not homes:
            continue
        valid, stale, unknown = [], [], False
        for src in homes:
            pool, vol = src[1:].split('/', 1)
            summ = sharesummary(pool, vol)
            rec = records.get(vol, [])
            recactive = len(rec) > 8 and rec[7] == ip and rec[-1] == 'active'
            if summ:
                sl = summ.split('/')
                if len(sl) > 8 and sl[7] == ip and sl[-1] == 'active':
                    valid.append((pool, vol, sl[8]))
                elif recactive:
                    unknown = True
                else:
                    stale.append(src)
            else:
                if not os.path.isdir('/'+pool) or recactive:
                    unknown = True
                else:
                    r = _runto(['zfs','list','-H','-o','name',pool+'/'+vol], out=False)
                    if r is None or r[0] == 0:      # dataset there, or zfs did not answer: unknown
                        unknown = True
                    else:
                        stale.append(src)
        if unknown or not stale:
            continue
        with open('/root/volumecheck.sweep','a') as f:
            f.write(str(datetime.datetime.now())+' '+cname+' stale '+' '.join(stale)+' valid '+' '.join(p+'/'+v for p,v,_ in valid)+'\n')
        if valid:
            pool, vol, sub = valid[0]
            cmdline = ['/TopStor/cifs.py', leader, leaderip, myhost, myhostip, leaderip, pool, vol, ip, sub, 'HOMEE']
        else:
            cmdline = ['/TopStor/VolumeDockerChange.py', ip, '24', 'HOMEE', stale[0][1:]]
        print('home sweep', cname, cmdline)
        subprocess.run(cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        done.append(cname)
    return done

def cleanfailed(dockers):
    fails = ['timeerror','ADnameerror', 'ADservererror']
    doms = [ (doc.split('-')[-1],doc.split(' ')[0]) for doc in dockers.split('\n') if 'CIFS_' in str(doc)]
    for dom in doms:
        cmdline = '/TopStor/getdomvolstatus.sh '+dom[0]
        result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('_result')[1]
        print('dock:',cmdline,'....',result)
        if result in fails:
            print('cleaning',dom[0],dom[1])
            cmdline = 'docker rm -f '+ dom[1]
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

 # QSD5.352 r9 (prover D5, validator r8 R3): on a follower the registry is read from the LEADER (the callers read the node's
 # own copy, which the sync loop refreshes seconds after a change: a home just changed or disabled was seen with its old
 # record).  Not answered (leader busy or gone): the node's copy, as before.
 if myhost != leader:
  try:
   lead = get(leaderip, 'volumes', '--prefix')
   if isinstance(lead, list) and lead and all(isinstance(e, (list, tuple)) for e in lead):
    etcds = lead
  except Exception as e:
   print('leader registry not read, the local copy is used', e)
 cmdline = 'docker ps'
 dockers = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 #cmdline = 'ls /TopStordata'
 #exports = subprocess.run(cmdline.split(),shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
 #cmdline = 'rm -rf /TopStordata/exportip*'
 #subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 #exports = glob('/pdhc*/exports*')
 with open('/root/volumecheck','w') as f:
  f.write(str(etcds))
 #exports = [ x.split('exports.')[1] for x in exports ]
 print('----------------------------------------------------')
 print(etcds,'\n',dockers)
 inspectall(dockers)
 # QSD5.352 (QC 706): drop registry keys without a record (value _1 / -1 / empty, written by the old VolumeActivateHome);
 # the leader only, its etcd is the one every node copies.
 if myhost == leader:
  dummies = [ e[0] for e in etcds if isinstance(e, (list, tuple)) and len(e) > 1 and str(e[0]).startswith('volumes/')
              and str(e[1]).strip() in ('_1', '-1', '') ]
  for key in dummies:
   print('removing the empty volume record', key)
   dels(leaderip, key)
  if dummies:
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   etcds = [ e for e in etcds if not (isinstance(e, (list, tuple)) and len(e) > 1 and e[0] in dummies) ]
 jobs = [lambda: nfsnew(etcds, replis, dockers), lambda: cifs(etcds, replis, dockers),
         lambda: homes(etcds, replis, dockers), lambda: iscsi(etcds, replis)]
 def runjob(j):
     try:
         j()
     except Exception as e:
         print('volumecheck job failed', e)
 with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
     list(ex.map(runjob, jobs))
 runjob(lambda: homesweep(etcds))
 cleanfailed(dockers) 
   
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
