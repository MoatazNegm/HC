#!/usr/bin/python3
import subprocess, sys
import os
from logqueue import queuethis, initqueue
from etcdput import etcdput as put
from etcdgetpy import etcdget as get 
from etcddel import etcddel as dels
from poolstoimport import getpoolstoimport, initgetpoolstoimport
from allphysicalinfo import getall 
from time import time as stamp
from time import sleep
from ast import literal_eval as mtuple


#leader=get('leader','--prefix')[0][0].split('/')[1]
stampi = str(stamp())

def selecthosting(minhost,hostname,hostpools):
 if len(hostpools) < minhost[1]:
  minhost = (hostname, len(hostpools))
 return minhost


def dosync(sync, *args):
  global leader, leaderip, myhost, myhostip, etcdip, stmapi
  #dels(leaderip, sync)  
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 

def selecthost(poolinfo,readies):
    global leader, leaderip, myhost, myhostip, etcdip, stmapi
    mincount = 1000000000 
    selectedhost = 'nohost'
    # QSD5.352 (QC 684): the next host of a pool is any ready node but the one that holds the pool now.  The leader skipped
    # ITSELF, so a pool held by a follower got that follower as its "next" host (useless when it dies), and a pool the leader
    # imported while it was alone kept poolnxt = the leader after the other node came back: when that leader was stopped the
    # survivor had no assignment and did not import the pool for ~5 minutes.  An exported pool (from 'zpool import') carries
    # the scanning node as its host, so it is the same rule as before for it.
    owner = poolinfo.get('host', myhost) if isinstance(poolinfo, dict) else myhost
    readyhosts = [ h[0].split('/')[1] for h in readies if isinstance(h, (list, tuple)) and len(h) > 0 and '/' in str(h[0]) ]
    if owner not in readyhosts:
        owner = myhost
    for hostinfo in readies:
        host = hostinfo[0].split('/')[1]
        if owner == host and len(readies) > 1  :
            continue   ########  pass this since we are searching for the next host 
        counts = list(str(poolinfo['raids'])).count(host)
        if counts  < mincount:
            selectedhost =  host
            mincount = counts
        #elif selectedhost[0] == counts:
        #    selectedhost[1] = selectedhost[1] + [ host ]
    return selectedhost
        
def foreignpool(pool):
 # container flavour: one kernel for every cluster, so a pool of ANOTHER cluster is visible here.  Its owner (zfs property
 # topstor:owner, /pace/cpoolowner.sh) is a host this cluster has never known (no ipaddr/<host> key): never import,
 # reguid or re-own such a pool, and drop what already points at it (seen in QC test 23, QSD5.280).
 if not (os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10')):
  return False
 try:
  owner = subprocess.run(['/pace/cpoolowner.sh','of',pool],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode().strip()
 except Exception:
  return False
 if owner in ('', '-', myhost):
  return False
 return str(get(leaderip,'ipaddr/'+owner)[0]) == '_1'

def ownedbylivepeer(pool):
 # container flavour: one kernel, so a pool that a node has just created is already "imported" here. The leader names a
 # standby (poolnxt) at once, and in the first seconds the pools list does not hold the pool yet: the standby "imported" it
 # (a no-op), took the owner property and left the creator holding the mount -- the pool then showed host UNAVAIL / not
 # balanced and its delete ended 'pool is busy' (QC test 10, QSD5.332).  A pool that is imported and whose owner is another
 # node that is still ready is not taken over; a dead owner is not in ready, so a real take over is not affected.
 if not (os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10')):
  return False
 if not os.path.exists('/proc/spl/kstat/zfs/'+pool):
  return False
 try:
  owner = subprocess.run(['/pace/cpoolowner.sh','of',pool],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30).stdout.decode().strip()
  if owner in ('', '-', myhost):
   return False
  return owner in str(get(leaderip,'ready','--prefix'))
 except Exception:
  return False

def destroyedpool(pool):
 # QSD5.345: DGdestroyPool leaves a tombstone destroyedpool/<pool> (leader etcd, copied to every node): a pool of that name
 # that shows up again in 'zpool import' is a stale leg of the deleted pool (its node was away at the delete) and is never
 # assigned, imported or re-registered here.  A pool the user imports on purpose (DGsetPool 'import') clears the tombstone.
 for ip in (leaderip, etcdip):
  try:
   if str(get(ip,'destroyedpool/'+pool)[0]) not in ('_1', '-1', '', 'None'):
    return True
  except Exception:
   pass
 return False

def poolonline(pool):
 # "zpool reguid / export / import ..." wait for a transaction group.  On a SUSPENDED pool (its disks are gone) that
 # wait never ends, in the kernel (state D, not killable), and it holds ZFS's global lock: after that every zpool /
 # zfs command on the host hangs until the host is rebooted (seen on 2026-10-07, twice).  So such a pool is left
 # alone here; /pace/closthost.sh (container flavour) gives it its disks back and resumes it first.
 try:
  with open('/proc/spl/kstat/zfs/'+pool+'/state') as f:
   return f.read().strip() in ('ONLINE', 'DEGRADED')   # DEGRADED answers; only SUSPENDED hangs
 except OSError:
  return False


def importedhere(pool):
 # r10f (D12): the pool is imported AND owned by this node.  Container flavour: one kernel, so 'imported' alone says
 # nothing; the owner property (cpoolowner.sh) must name this node exactly (an unknown owner '' / '-' is not enough: a
 # pool left imported by a node that died is taken over through the import below).  Physical: imported here.
 if not poolonline(pool):
  return False
 if os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10'):
  try:
   res = subprocess.run(['/pace/cpoolowner.sh','of',pool],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
   return res.stdout.decode('utf-8','replace').strip() == myhost
  except Exception:
   return False
 return True

def poolishere(pool):
 # container flavour: one kernel, the owner is written on the pool; physical: the pool is imported here or it is not
 if os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10'):
  try:
   res = subprocess.run(['/pace/cpoolowner.sh','of',pool],stdout=subprocess.PIPE,timeout=30)
   return res.stdout.decode('utf-8','replace').strip() in (myhost, '')
  except Exception:
   return True       # unknown: keep the marker
 return os.path.exists('/proc/spl/kstat/zfs/'+pool)


def memberimportdir(pool, disks):
 # a directory of symlinks to the by-id devices (and their partitions) of the disks etcd lists in <pool>; '' when none is present
 import glob
 impdir = '/tmp/impdir-'+pool
 subprocess.run(['rm','-rf',impdir])
 os.makedirs(impdir, exist_ok=True)
 found = 0
 for name, d in disks.items():
  if d.get('pool') != pool:
   continue
  for key in ('actualdisk','zname','name'):
   dname = str(d.get(key,'')).replace('/dev/disk/by-id/','')
   if dname and dname != '_1':
    for dev in glob.glob('/dev/disk/by-id/'+dname+'*'):
     link = impdir+'/'+os.path.basename(dev)
     if not os.path.exists(link):
      os.symlink(dev, link)
      found += 1
 if found == 0:
  return ''
 return impdir

def importscan(impdir):
 # r10h (finding 3): the pools 'zpool import -d <impdir>' lists, as [{'name','id','state','members'}]
 cmd = ['timeout','60','/usr/sbin/zpool','import'] + (['-d', impdir] if impdir else [])
 try:
  out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode('utf-8','replace')
 except Exception:
  return []
 res = []
 cur = None
 inconfig = False
 for line in out.split('\n'):
  w = line.split()
  if len(w) >= 2 and w[0] == 'pool:':
   cur = {'name': w[1], 'id': '', 'state': '', 'members': []}
   res.append(cur)
   inconfig = False
  elif cur is None or not w:
   continue
  elif w[0] == 'id:' and len(w) >= 2:
   cur['id'] = w[1]
  elif w[0] == 'state:' and len(w) >= 2:
   cur['state'] = w[1]
  elif w[0] == 'config:':
   inconfig = True
  elif inconfig and len(w) >= 2 and w[0] != cur['name'] and not w[0].startswith(('mirror', 'raidz', 'spare', 'cache', 'logs', 'replacing', 'draid')):
   cur['members'].append(w[0])
 return res

def importbyname(pool, poolid, impdir):
 # QSD5.352 r10h (QC proof 10g finding 3): an import by the published id (ActPool/<pool>) that fails is retried by name
 # ONLY when that is safe: etcd lists member disks of the pool (impdir), the id is not among the pools on those disks at
 # all (the published id is stale, finding 5), and exactly ONE pool of that name is there and it is ONLINE (every member
 # present with the same, newest label).  Several pools of that name (a stale leg of an older id: QSD5.304 lost data that
 # way), or only a DEGRADED one, are never imported by name: the candidates are logged and nothing is done.
 # Returns (id or None, why).
 if not impdir:
  return None, 'no import by name: etcd lists no member disk of '+pool
 cands = [c for c in importscan(impdir) if c['name'] == pool]
 desc = ', '.join(c['id']+' '+c['state']+' ('+' '.join(c['members'])+')' for c in cands) or 'none'
 if any(c['id'] == str(poolid) for c in cands):
  return None, 'no import by name: id '+str(poolid)+' is on the member disks ('+desc+')'
 if len(cands) != 1:
  return None, 'no import by name: '+str(len(cands))+' pools named '+pool+' on the member disks: '+desc
 if cands[0]['state'] != 'ONLINE' or not cands[0]['id'].isdigit():
  return None, 'no import by name: the only pool named '+pool+' on the member disks is not ONLINE: '+desc
 return cands[0]['id'], 'import by name: id '+str(poolid)+' is not on the member disks, the only pool named '+pool+' there is '+desc

ACTLOG = '/root/actpoolreconcile.log'
def actpoolreconcile(mypools):
 # QSD5.352 r10h (QC proof 10g finding 5, new-leader variant): after a take over the new owner imported P1 by its id and
 # gave it a new one (reguid), but the put of ActPool/<pool> went to the cluster address while the leadership moved: the
 # leader kept the OLD id (the next leader stop would import by a dead id; repaired by hand in the proof).  The owner of
 # an imported pool now compares, every pass, the id the leader publishes with the pool's live guid and puts the live one
 # (with the same sync request as after an import) when they differ.  Only existing ActPool keys are corrected.
 for v in mypools:
  pool = str(v.get('name','')) if isinstance(v, dict) else ''
  if not pool or 'pree' in pool:
   continue
  try:
   if str(get(leaderip,'destroying/'+pool)[0]) != '_1' or destroyedpool(pool):
    continue
   pub = str(get(leaderip,'ActPool/'+pool)[0])
   if pub in ('_1','-1','','None') or not importedhere(pool):
    continue
   live = subprocess.run(['timeout','20','/sbin/zpool','get','-H','-o','value','guid',pool],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode().strip()
  except Exception:
   continue
  if not live.isdigit() or live == pub:
   continue
  dels(leaderip,'sync/ActPool', pool)
  put(leaderip,'ActPool/'+pool,live)
  dosync('actpool_', 'sync/ActPool/Add_'+pool+'_'+live+'/request','actpool_'+str(stamp()))
  try:
   with open(ACTLOG,'a') as f:
    f.write(subprocess.run(['date','+%F %T'],stdout=subprocess.PIPE).stdout.decode().strip()+' '+myhost+' '+pool+': leader '+leaderip+' published '+pub+', live guid '+live+': corrected\n')
  except Exception:
   pass

DECISIONF = '/root/zpooltoimport.last'
def lastdecisions():
 # r10d (validator 10c D5): the last decision per pool is kept in a file, one 'pool<TAB>why' line each: the looper
 # (zpooltoimportlooper.sh) starts this script as a NEW process every 9 s, so a module dict de-duplicated nothing and a
 # lasting skip was logged again every round.  zfsping.py runs it in its own process too: both share the file.
 d = {}
 try:
  with open(DECISIONF) as f:
   for line in f:
    k, tab, v = line.rstrip('\n').partition('\t')
    # r10f (QC proof 10e D11): only 'pool<TAB>why' lines are decisions; a line without a tab (a torn or foreign line)
    # was kept as a pool named after the whole line and written back by every later save
    if k and tab:
     d[k] = v
 except Exception:
  pass
 return d

def savedecisions(d):
 try:
  tmp = DECISIONF+'.'+str(os.getpid())
  with open(tmp, 'w') as f:
   for k, v in d.items():
    f.write(k+'\t'+v+'\n')
  os.replace(tmp, DECISIONF)
 except Exception:
  pass

def forgetdecision(pool):
 d = lastdecisions()
 if d.pop(pool, None) is not None:
  savedecisions(d)

def decision(pool, why):
 # QSD5.352 r10c (QC proof T1): a pool assigned here (poolnxt) was not imported for 312 s once (z1) and within 15 s the
 # next time (z2), and nothing said why.  Every assigned pool's decision is logged with a time stamp to
 # /root/zpooltoimport.log when it changes (this runs every 9 s), so the next run shows which test skipped it.
 why = why.replace('\t', ' ').replace('\n', ' ')
 d = lastdecisions()
 if d.get(pool) == why:
  return
 d[pool] = why
 savedecisions(d)
 try:
  if os.path.exists('/root/zpooltoimport.log') and os.path.getsize('/root/zpooltoimport.log') > 5000000:
   os.replace('/root/zpooltoimport.log', '/root/zpooltoimport.log.1')
  with open('/root/zpooltoimport.log','a') as f:
   f.write(subprocess.run(['date','+%F %T'],stdout=subprocess.PIPE).stdout.decode().strip()+' '+myhost+' '+pool+': '+why+'\n')
 except Exception:
  pass

LOCKF = '/run/zpooltoimport.lock'
def importlock():
 # r10f (QC proof 10e D12): one import pass at a time on a node.  The looper (zpooltoimportlooper.sh, a new process every 9 s)
 # and zfsping.py's refreshall() on a leader change both run this pass; a second pass that read the assignment while the
 # first one was importing (an import of a taken-over pool took 58 s) imported the same pool again 1 s after the first
 # finished ('importing' / 'imported' twice, a second reguid and a second pools sync).  A pass that finds the lock taken
 # does nothing (the next round, 9 s later, sees the result of the first).  Unknown lock problems never stop the import.
 try:
  import fcntl
  f = open(LOCKF, 'a')
 except Exception:
  return 'nolock'
 try:
  fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
  return f
 except (BlockingIOError, PermissionError):
  f.close()
  return None
 except Exception:
  f.close()
  return 'nolock'

def zpooltoimport(*args):
 if args and args[0] == 'init':
  return _zpooltoimport(*args)
 lock = importlock()
 if lock is None:
  print('another import pass runs on this node, this one is skipped')
  return
 try:
  return _zpooltoimport(*args)
 finally:
  if lock != 'nolock':
   lock.close()

def _zpooltoimport(*args):
 global leader, leaderip, myhost, myhostip, etcdip
 if args[0]=='init':
     leader = args[1]
     leaderip = args[2]
     myhost = args[3]
     myhostip = args[4]
     etcdip = args[5]
     initqueue(leaderip, myhost) 
     initgetpoolstoimport(leader,leaderip,myhost,myhostip)
     return
 poouids = get(etcdip,'poouids',myhost) 
 nextpools=get(leaderip, 'poolnxt', '--prefix') 
 if 'not reachable' in str(nextpools):
        return
 needtoimport=[ x for x in nextpools if myhost in str(x)] 
 pools = [v for k,v in getall(leaderip)['pools'].items()]
 mypools = [v  for v in pools if v['host'] == myhost ]
 if 'not reachable' in str(pools):
        return
 if '_1' in str(poouids):
    poouids = []
 for poo in poouids:
    print('poouids start')
    pool=poo[0].split('/')[1]
    # Ours is decided by the pool itself (owner property / imported here), not by the pools list of etcd: right after a
    # take over that list still names the old host for a few seconds, the marker was dropped in that window and the pool kept
    # its old id for ever (seen in QC test 14, QSD5.304: the returning node imported its stale leg and the data was lost).
    if not poolishere(pool) or destroyedpool(pool):
        dels(etcdip, 'poouids/'+pool)      # the pool is not ours any more (taken over elsewhere or deleted): nothing to retry here
        continue
    if str(get(leaderip,'destroying/'+pool)[0]) != '_1':
        continue                           # QSD5.345: being destroyed: no reguid, no new ActPool/<pool> meanwhile
    if poolonline(pool):
        cmdline = 'zpool reguid '+pool
        result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        with open('/root/poouids.log','a') as f:
            f.write(str(stamp())+' '+pool+' reguid rc='+str(result.returncode)+' '+result.stderr.decode('utf-8','replace')+'\n')
        if result.returncode == 0:
            print('done')
            cmdline="zpool get guid "+pool+" -H "
            guid=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split()[2]
            dels(leaderip,'sync/ActPool', pool)
            put(leaderip,'ActPool/'+pool,guid)
            dosync('actpool_', 'sync/ActPool/Add_'+pool+'_'+guid+'/request','actpool_'+str(stamp()))
            dels(etcdip, 'poouids/'+pool) 
        else:
            print('pool not ready yet')
 actpoolreconcile(mypools)      # r10h (finding 5)
 if myhost not in str(needtoimport):
  print(needtoimport)
  print('no need to import a pool here')
                  
 else:
  for poolline in needtoimport:
   pool = poolline[0].replace('poolnxt/','')
   if pool in str(pools):
    holder = [ str(v.get('host','?')) for v in pools if isinstance(v, dict) and v.get('name') == pool ]
    decision(pool, 'skipped: the cluster pools list still has it (host '+(','.join(holder) or 'substring match')+')')
    continue
   if foreignpool(pool):
    print('pool of another cluster, not imported', pool)
    decision(pool, 'skipped: pool of another cluster')
    dels(leaderip, 'poolnxt', pool)
    dels(leaderip, 'pools', pool)
    continue
   if str(get(leaderip,'destroying/'+pool)[0]) != '_1':
    print('pool is being destroyed, not imported', pool)
    decision(pool, 'skipped: being destroyed')
    continue
   if destroyedpool(pool):
    print('pool was deleted, a stale copy is not imported', pool)
    decision(pool, 'skipped: tombstoned (destroyedpool)')
    dels(leaderip, 'poolnxt/'+pool)
    continue
   if ownedbylivepeer(pool):
    print('pool is imported and owned by a live node, not taken over', pool)
    decision(pool, 'skipped: imported and owned by a live node')
    continue
   print('pool to be imported now', pool)
   # the assignment may have been withdrawn since the list was read (DGdestroyPool exports the pool for a moment): a pool that
   # is being destroyed must not be taken over here (QSD5.325)
   if str(get(leaderip,'poolnxt/'+pool)[0]) != myhost:
    print('assignment of', pool, 'withdrawn, not imported')
    decision(pool, 'skipped: assignment withdrawn')
    continue
   # r10f (D12): the pool list of this pass may be older than an import that ended meanwhile (in another process before
   # this pass took the lock): a pool that is ONLINE here with this node as its owner is not imported a second time
   if importedhere(pool):
    print('pool is already imported by this node, not imported again', pool)
    decision(pool, 'skipped: already imported by this node')
    forgetdecision(pool)
    dels(leaderip, 'poolnxt', pool)
    continue
   poolid = get(leaderip,'ActPool/'+pool)[0]
   if poolid == '_1':
    poolid = pool
   # Import only from the disks that are members of this pool (etcd), so a stale leg that kept the pool's name but was
   # detached while its node was away (old guid, free disk now) can never be imported as the pool and then be re-attached over.
   cmdline= '/usr/sbin/zpool import '+poolid
   impdir = memberimportdir(pool, getall(leaderip)['disks'])
   if impdir:
    cmdline= '/usr/sbin/zpool import -d '+impdir+' '+poolid
   # poolnxt/<pool> is the only trigger of this import: it is deleted only after the import worked (below).  It used to be deleted here,
   # before the import, so one failed first try (the disk session of the survivor was not up yet after a take over) orphaned the pool for ever.
   print(cmdline)
   decision(pool, 'importing: '+cmdline)
   put(leaderip, 'pools/'+pool,myhost)
   res = subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   failnote = ''
   if res.returncode != 0:
    # r10h (finding 3): why the import failed was thrown away ("import failed (rc 1)" 84 times, nothing else)
    failnote = ': '+res.stderr.decode('utf-8','replace').strip().replace('\n',' | ')[:300]
    alt, why = importbyname(pool, poolid, impdir)
    failnote += '; '+why
    if alt:
     decision(pool, 'import of '+str(poolid)+' failed (rc '+str(res.returncode)+')'+failnote)
     cmdline = '/usr/sbin/zpool import -d '+impdir+' '+alt
     res = subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
     if res.returncode != 0:
      failnote += '; import of '+alt+' failed too: '+res.stderr.decode('utf-8','replace').strip().replace('\n',' | ')[:300]
   result = res.stdout.decode('utf-8')
   sleep(1)
   cmdline= '/usr/sbin/zpool status  '
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print('result',result)
   if pool in result and poolonline(pool):
    decision(pool, 'imported')
    forgetdecision(pool)
    dels(leaderip, 'poolnxt', pool )      # imported: the assignment is done
    # The pool is imported by its id (ActPool/<pool>), and a new id is given right after the import, so the next import
    # (by the id every node knows) finds only the devices that took part in THIS import: a disk that was away meanwhile
    # keeps the old id and can no longer be imported as the pool.  ZFS refuses 'zpool reguid' on a pool that is not healthy,
    # and after a take over the pool is degraded (the dead node's disk is missing) until the missing disk is replaced.
    # That refusal was ignored: the old id was stored again, nothing retried, and the next take over imported the stale
    # disk of the dead node and lost what had been written meanwhile.  Now a refused reguid keeps the old id published
    # and leaves a retry marker (poouids/<pool>) that the loop at the top of this function works off as soon as the pool is healthy.
    cmdline = 'zpool reguid '+pool
    result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode == 0:
       print('done')
       cmdline="zpool get guid "+pool+" -H "
       guid=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split()[2]
       dels(leaderip,'sync/ActPool', pool)
       put(leaderip,'ActPool/'+pool,guid)
       dosync('actpool_', 'sync/ActPool/Add_'+pool+'_'+guid+'/request','actpool_'+str(stamp()))
       dels(etcdip, 'poouids/'+pool) 
    else:
       print('reguid refused (pool not healthy yet), retried later:', result.stderr.decode('utf-8','replace'))
       put(etcdip, 'poouids/'+pool, myhost)

    # container flavour: the pool is visible in every node (one kernel), its owner is written on the pool
    if os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10'):
        subprocess.run(['/pace/cpoolowner.sh','set',myhost,pool])
    # the cache (L2ARC) must sit on the node that owns the pool: a cache disk of another -- or a lost -- node is
    # replaced by a local one.  DGsetPool did this for a manual import only; a pool taken over after its owner
    # died comes through here.
    # QSD5.352 r10 (QC 631): in the background, in 'wait' mode: the cluster info lists the pool under this node only after
    # the pools sync below and the next putzpool; run in line (and once) it found no pool and the cache stayed UNAVAIL.
    try:
        with open('/root/fixcachelocality.log','a') as f:
            f.write(str(stamp())+' '+pool+' '+myhost+' (wait mode, background)\n')
            f.flush()
            subprocess.Popen(['/usr/bin/python3','/TopStor/fixcachelocality.py',leaderip,pool,myhost,'wait'],
                             stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        print('fixcachelocality failed:',e)
    put(etcdip, 'dirty/volume','0')
    #put(etcdip, 'poouids/'+pool,myhost)
    print('before sync')
    print('sync pools Add')
    dels(leaderip,'sync/pools', pool)
    dosync('pools_', 'sync/pools/Add_'+pool+'_'+myhost+'/request','pools_'+str(stamp()))
    print('pools_', 'sync/pools/Add_'+pool+'_'+myhost+'/request','pools_'+str(stamp()))
    print('After sync')
    #cmdline= 'systemctl restart zfs-zed  '
    #result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   else:
    decision(pool, 'import failed (rc '+str(res.returncode)+'), retried in the next round'+failnote)
    dels(leaderip, 'pools/',pool)         # not imported (yet): poolnxt stays, the next round (9 s) tries again
        
    
 if myhost != leader:
  return

 readies=get(etcdip,'ready','--prefix')
 hosts=get(leaderip,'host','/current')
 
 #pools = [poolinfo[0].split('/')[1]+'_'+poolinfo[1] for poolinfo in pools ]
 activepools = get(leaderip, 'ActPool','--prefix')
 notactivepools = getpoolstoimport()
 cpools = pools
 for notpo in notactivepools:
    notpname = notpo['name']
    notpid = notpo['guid'] 
    # container flavour: one kernel for every cluster, so an EXPORTED pool of another cluster (its owner node is down or
    # stopped, the pool is listed by "zpool import" and has no readable owner property) looks like a pool nobody knows.
    # This cluster has never had it (no ActPool/<pool>, not in pools/): never assign it (QC test 21, QSD5.315).
    if (os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10')) and notpname not in str(activepools):
        continue
    if destroyedpool(notpname):
        continue      # QSD5.345: a stale copy of a deleted pool (both flavours)
    if (notpname in str(activepools) and (notpid in str(activepools) or len(readies) == 1)) or notpname not in str(activepools): 
        cpools = cpools + [notpo] 
    #if len(readies) == 1:
    #    dels(leaderip, 'ActPool/'+notpname)
 
 importedpools = set(str(p.get('name')) for p in pools if isinstance(p, dict))
 for poolinfo in cpools:
    pool = poolinfo['name']
    if 'pree' in pool:
     continue
    # QSD5.352 (QC 684): an imported pool is always re-checked; poolnxt naming this leader (written while it was alone)
    # kept the pool in needtoimport and was never moved to the node that came back
    if pool not in str(needtoimport) or (pool in importedpools and len(readies) > 1):
        nxthost=selecthost(poolinfo,readies)
        print('nxthosts',nxthost)
        poolnxt=get(leaderip,'poolnxt/'+pool)[0]
        # exact comparison: "poolnxt in str(nxthost)" was True for an EMPTY stored value ('' is a substring of every
        # string), so a pool whose poolnxt had been emptied was never assigned to a node again and never imported
        if poolnxt == nxthost:
            continue 
        print('adding')
        decision('leader:'+pool, 'poolnxt '+str(poolnxt)+' -> '+str(nxthost)+' (ready: '+' '.join(sorted(str(h[0]).split('/')[-1] for h in readies if isinstance(h,(list,tuple))))+')')
        #dels(leaderip,'poolnxt/'+pool)
        put(leaderip,'poolnxt/'+pool,nxthost)
        print('sync poolnxt Add',nxthost,pool)
        dels(leaderip,'sync/poolnxt',pool)
        dosync('poolnxt', 'sync/poolnxt/Add_'+pool+'_'+nxthost+'/request','poolnxt_'+str(stamp()))
 return
     
       
if __name__=='__main__':
    import sys
    if len(sys.argv) == 5:
        leader=sys.argv[1]
        leaderip=sys.argv[2]
        myhost=sys.argv[3]
        myhostip=sys.argv[4]
    else:
        print('sysargv',len(sys.argv))
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
        leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
        leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
        myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
        myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    if leader == myhost:
        etcdip = leaderip 
    else:
        etcdip = myhostip
    initqueue(leaderip, myhost) 
    initgetpoolstoimport(leader,leaderip,myhost,myhostip)
    zpooltoimport('hi')
