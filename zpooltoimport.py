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
from time import sleep, strftime, localtime
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


def membernames(pool, disks, strict=False):
 # the disk names etcd lists as members of <pool>; strict (what is remembered): no guid-named legs, stand-ins or 'None'
 names = []
 for name, d in disks.items():
  if not isinstance(d, dict) or d.get('pool') != pool:
   continue
  for key in ('actualdisk','zname','name'):
   dname = str(d.get(key,'')).replace('/dev/disk/by-id/','')
   if not dname or dname == '_1' or dname in names:
    continue
   if strict and (dname == 'None' or dname.isdigit() or dname.startswith('dm-')):
    continue
   names.append(dname)
 return names

# r10i (QC proof 10h F2: 745.2, 746.2): the member disks come from the cluster disk map, and that map is made of what each
# READY node publishes (hosts/<host>/current) about the pools IT owns.  When the owner stops, hostlost deletes its hosts/
# keys, and the disks of its pools -- also the ones on the surviving node -- are listed as free ('pree'): memberimportdir()
# found no member, the import ran without '-d' and the by-name fallback always said 'etcd lists no member disk'.  Every node
# now remembers, each import pass, the members the map lists for every pool (/root/poolmembers.last, replaced whenever the
# map lists the pool again, so a leg that was detached meanwhile is not kept); the import uses that list when the live map
# has no member.  Entries not refreshed for MEMBERKEEP s are dropped.  Container flavour only.
MEMBERF = '/root/poolmembers.last'
MEMBERKEEP = 7*86400
MEMBERREFRESH = 600
def lastmembers():
 import json
 try:
  with open(MEMBERF) as f:
   d = json.load(f)
  return d if isinstance(d, dict) else {}
 except Exception:
  return {}

def remembermembers(disks):
 import json
 old = lastmembers()
 now = stamp()
 new = {}
 pools = set(str(d.get('pool','')) for d in disks.values() if isinstance(d, dict) and 'pdhcp' in str(d.get('pool','')))
 for pool in pools:
  names = membernames(pool, disks, strict=True)
  if names:
   new[pool] = {'stamp': now, 'members': names}
 for pool, v in old.items():
  try:
   if pool not in new and now - float(v.get('stamp', 0)) < MEMBERKEEP:
    new[pool] = v
  except Exception:
   pass
 # unchanged members of a pool keep their stamp for up to MEMBERREFRESH s: the file is not rewritten every 9 s
 for pool, v in list(new.items()):
  try:
   if pool in old and old[pool].get('members') == v.get('members') and now - float(old[pool].get('stamp', 0)) < MEMBERREFRESH:
    new[pool] = old[pool]
  except Exception:
   pass
 if new == old:
  return
 try:
  tmp = MEMBERF+'.'+str(os.getpid())
  with open(tmp, 'w') as f:
   json.dump(new, f)
  os.replace(tmp, MEMBERF)
 except Exception:
  pass

MEMBERSRC = {}
def importnames(pool, disks):
 # the disk names to import <pool> from: the members the live map lists; container flavour: when it lists none, the
 # members it listed last (r10i F2).  MEMBERSRC[pool] names the source for the decision line.
 names = membernames(pool, disks)
 MEMBERSRC[pool] = 'etcd'
 if not names and iscontainer():
  # r10i (F2): the live map has no member (the owner that published it is gone): the members it listed last
  last = lastmembers().get(pool, {})
  names = [str(n) for n in last.get('members', []) if str(n)]
  try:
   MEMBERSRC[pool] = 'members as last listed '+str(int(stamp()-float(last.get('stamp', 0))))+' s ago' if names else 'none'
  except Exception:
   MEMBERSRC[pool] = 'members as last listed' if names else 'none'
 return names

def memberimportdir(pool, disks):
 # a directory of symlinks to the by-id devices (and their partitions) of the disks etcd lists in <pool>; '' when none is present
 # r10j (R1): used by the PHYSICAL flavour only (one mount namespace there); the container flavour uses memberdevs()
 import glob
 impdir = '/tmp/impdir-'+pool
 subprocess.run(['rm','-rf',impdir])
 os.makedirs(impdir, exist_ok=True)
 found = 0
 names = importnames(pool, disks)
 for dname in names:
    for dev in glob.glob('/dev/disk/by-id/'+dname+'*'):
     link = impdir+'/'+os.path.basename(dev)
     if not os.path.exists(link):
      os.symlink(dev, link)
      found += 1
 if found == 0:
  return ''
 return impdir

# r10j (QC proof 10i R1, 775.1 / 778.1 / 787.2): in the container flavour 'zpool import -d /tmp/impdir-<pool>' can never
# import.  The vdev paths ZFS takes from the directory (/tmp/impdir-<pool>/<disk>-part1) are opened by the KERNEL, in the
# host's mount namespace, which has /dev/disk/by-id/ (same kernel, host udev) but not the container's /tmp: every leg found
# through the dir is UNAVAIL ('was /tmp/impdir-...').  After an owner's stop the survivor never imported (rc 1 for 22 min),
# or imported a mirror half (its LOCAL leg UNAVAIL, only the stopping node's leg live) that SUSPENDED a moment later when
# that node's target went away.  Now each member is passed as its own '-d /dev/disk/by-id/<disk>-part1' (the option can be
# repeated; the scan still reads ONLY the member disks, so a stale detached leg of the same name is still never imported,
# QSD5.304).  Container flavour only; the physical flavour keeps its /tmp/impdir (one namespace there).
BYID = '/dev/disk/by-id/'
def namedev(dname):
 # the by-id device of a member disk name that carries the ZFS label: <disk>-part1 for a whole disk, the name itself for a
 # partition name or when no -part1 link exists (yet); never the reserved -part9.  '' when none exists.
 import re
 dname = str(dname).replace(BYID, '')
 if not dname or '/' in dname:
  return ''
 cands = [BYID+dname] if re.search(r'-part[0-9]+$', dname) else [BYID+dname+'-part1', BYID+dname]
 for c in cands:
  if c.endswith('-part9'):
   continue
  if os.path.exists(c):
   return c
 return ''

def memberdevs(pool, disks):
 # the device (namedev) of each member disk name; [] when no member device is present
 devs = []
 for dname in importnames(pool, disks):
  c = namedev(dname)
  if c and c not in devs:
   devs.append(c)
 return devs

# r10n (validator 10m V-1, MEDIUM): round 10m took the devices of a list-only scan only when NO member device was found by
# name.  When only SOME member links are missing (the same "links gone for a moment" cause that emptied P1's list in r561
# can empty part of a list) the import used the subset: a mirror of a local leg with a late link (L1) and a leg on the
# leaving node (R1) was held on R1 alone ("every present member disk (1) is on <host>'s target") and then imported with
# '-d R1' only, a mirror half on disks about to vanish.  Now a member disk counts as found only when one of ITS names has a
# device; when any member disk is missing, the scan's devices of the same pool block are added (union) before the hold.
def membergroups(pool, disks):
 # the member disks of <pool>, each as the list of its names (actualdisk / zname / name); the remembered members (r10i F2,
 # used when the live map lists none) are one name per disk
 groups = []
 for d in disks.values():
  if not isinstance(d, dict) or d.get('pool') != pool:
   continue
  g = []
  for key in ('actualdisk','zname','name'):
   dname = str(d.get(key,'')).replace(BYID, '')
   if dname and dname != '_1' and dname not in g:
    g.append(dname)
  if g:
   groups.append(g)
 if not groups and iscontainer():
  groups = [[str(n)] for n in lastmembers().get(pool, {}).get('members', []) if str(n)]
 return groups

def missingmembers(pool, disks):
 # the member disks of <pool> none of whose names has a device here (each as its first name)
 return [g[0] for g in membergroups(pool, disks) if not any(namedev(n) for n in g)]

# r10n (validator 10m V-4, MEDIUM): the container's /dev is a tmpfs; its by-id links are made only by /pace/cdiskids.sh
# (sysfs only, cheap), which iscsiwatchdog.sh runs once per loop (minutes apart under load).  udev does not run in the
# container.  A member link that is missing is first made from sysfs NOW, then the members are looked up again.
CDISKIDS = '/pace/cdiskids.sh'
def cdiskids():
 try:
  subprocess.run(['timeout','20',CDISKIDS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  return True
 except Exception:
  return False

def samedev(a, b):
 try:
  return os.path.realpath(a) == os.path.realpath(b)
 except Exception:
  return a == b

def importargs(pool, disks):
 # the '-d' options of the import of <pool>: container: one '-d <device>' per member device (memberdevs); physical: as
 # before, '-d /tmp/impdir-<pool>' when a member is present.  [] = no member found: import by id with the default scan.
 if iscontainer():
  args = []
  for d in memberdevs(pool, disks):
   args += ['-d', d]
  return args
 impdir = memberimportdir(pool, disks)
 return ['-d', impdir] if impdir else []

def scanargs(impargs):
 # importscan / importbyname take the import arguments of the pass (a list) or, as before r10j, an import dir (a string)
 if isinstance(impargs, (list, tuple)):
  return list(impargs)
 return ['-d', impargs] if impargs else []

def validpoolname(name):
 # r10j (R1, putzpool): a ZFS pool name begins with a letter.  A name of digits only is a vdev guid that putzpool once
 # took for a pool line ('<guid> UNAVAIL ... was /tmp/impdir-<pool>/...'): pools/<guid> and poolnxt/<guid> were written and
 # both nodes ran 'zpool import <guid>' every 10 s.
 import re
 return bool(re.match(r'^[A-Za-z][A-Za-z0-9_.:-]*$', str(name)))

def iscontainer():
 # r10h pass 2 (validator G8): the r10h changes of this file (findings 5 and 3) are for the container flavour only; the
 # physical path stays as it was (CLAUDE.md hard rule 1).  The same test as flavor.sh.
 return os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv') or os.path.isdir('/sys/class/net/eth10')

# r10k (validator 10j G1, HIGH): the survivor already holds poolnxt/<pool> when the owner stops.  The owner exports its pool
# (cstop.sh, stopnode.sh) and only THEN logs out / takes its iSCSI target away; in that window the survivor imports the
# pool as soon as the cluster pools list drops it (+5 s in proof 10i x3).  A pool whose members are ALL served by the
# leaving node's target was imported on disks that vanished a moment later: both legs lost, SUSPENDED (host hang risk).
# The broken /tmp impdir of round 10i hid this (those imports always failed); the r10j by-id options make them work.
# Now (container flavour) the import waits while the pool cannot run without the member disks served by ANOTHER node's
# target (every present member, or a raidz / mirror that would lose too many of them: the vdev tree of a list-only
# 'zpool import' of the members) and that node is still ready (at most HOLDMAX s), its session is not LOGGED_IN (the
# disks are going away), or it left 'ready' less than HOLDMIN s ago with its target still up.  A pool with enough members
# elsewhere (PX: a mirror with a leg on this node, PR3: a raidz1 with one leg on the leaving node) is imported at once.
# The node that serves a disk is the host in its iSCSI target name (iqn.2016-03.com.<host>:t1, caddtargetdisks.sh), read
# from sysfs only (nothing that can hang).  The hold is logged as the pool's decision; poolnxt stays, the next round retries.
SYSBLOCK = '/sys/class/block/'
ISCSISESS = '/sys/class/iscsi_session/'
HOLDF = '/root/zpooltoimport.hold'
HOLDMAX = 120
HOLDMIN = 30
# r10l (validator 10k K1, K2): a hold entry is {host, first, last, notready}.  'last' is the time of the latest pass that
# judged the pool (held or ended); an entry whose 'last' is more than HOLDGAP s old belongs to an earlier leave and a NEW
# hold starts (round 10k reused its 'first': a later leave of the same owner was imported at once, inside the export ->
# logout window).  'notready' is when the pass first saw the host out of ready/ (cleared when it is ready again): HOLDMIN
# counts from it, not from the start of the hold.  Entries of pools this pass did not judge are dropped at the end of the
# pass (the owner took the pool back, poolnxt moved, assignment withdrawn).  Passes run every ~9 s; if they are ever more
# than HOLDGAP s apart a ready-hold starts again each time (longer wait, never an earlier import).
HOLDGAP = 60
HOLDSEEN = set()
def targetof(dev):
 # (host, session state) of the iSCSI target that serves <dev>; ('', '') when it is no iSCSI disk or cannot be told
 import re
 try:
  blk = os.path.basename(os.path.realpath(dev))
  m = re.search(r'/(session[0-9]+)/', os.path.realpath(SYSBLOCK+blk)+'/')
  if not m:
   return ('', '')
  with open(ISCSISESS+m.group(1)+'/targetname') as f:
   tn = f.read().strip()
  try:
   with open(ISCSISESS+m.group(1)+'/state') as f:
    st = f.read().strip()
  except OSError:
   st = ''
  h = re.match(r'^iqn\.[0-9]{4}-[0-9]{2}\.[^.:]+\.([^:]+):', tn)
  return (h.group(1) if h else '', st)
 except Exception:
  return ('', '')

def vdevtree(out, pool, poolid=''):
 # the top-level vdevs of <pool> in a 'zpool import' listing: [{'name','section','state','leaves':[(name, state)]}]
 # (the block whose id is <poolid>, else the only block named <pool>); None when it is not listed or not one
 blocks = []
 cur = None
 for line in out.split('\n'):
  w = line.split()
  if len(w) >= 2 and w[0] == 'pool:':
   cur = {'name': w[1], 'id': '', 'config': False, 'base': None, 'section': 'data', 'tops': []}
   blocks.append(cur)
   continue
  if cur is None or not w:
   continue
  if w[0] == 'id:' and len(w) >= 2 and not cur['config']:
   cur['id'] = w[1]
   continue
  if w[0] == 'config:':
   cur['config'] = True
   continue
  if not cur['config'] or w[0] in ('NAME', 'errors:') or line.endswith(':'):
   continue
  ind = len(line.expandtabs(8)) - len(line.expandtabs(8).lstrip())
  st = w[1] if len(w) > 1 else ''
  if cur['base'] is None:
   cur['base'] = ind                      # the pool line
   continue
  if ind <= cur['base']:
   cur['section'] = w[0]                  # logs / cache / spares / special / dedup
   continue
  if ind == cur['base'] + 2 or not cur['tops']:
   cur['tops'].append({'name': w[0], 'section': cur['section'], 'state': st, 'leaves': [], 'sub': []})
  else:
   if ind == cur['base'] + 4:
    cur['tops'][-1]['leaves'].append((w[0], st))     # direct children only (a nested replacing / spare counts by its state)
   cur['tops'][-1]['sub'].append((ind, w[0], st))    # r10n (V-10): every line below the top vdev, any depth
 # r10n (validator 10m V-10): 'devs' = the leaf devices of each top vdev at ANY depth.  The children of a nested spare-N /
 # replacing-N (an active hot spare, a running replace: base+6) were dropped, so the scan path judged and imported only
 # part of the pool's devices.  A line is a leaf when the next line of the same top vdev is not deeper.
 for b in blocks:
  for t in b['tops']:
   sub = t.pop('sub', [])
   t['devs'] = [(n, s) for i, (ind, n, s) in enumerate(sub) if i + 1 >= len(sub) or sub[i + 1][0] <= ind] if sub else [(t['name'], t['state'])]
 named = [b for b in blocks if b['name'] == pool]
 for b in named:
  if poolid and b['id'] == str(poolid):
   return b['tops']
 return named[0]['tops'] if len(named) == 1 else None

def survives(tops, lost):
 # True when every top-level data vdev keeps running without the disks in <lost> (base names) and the ones already missing
 import re
 def base(n):
  return re.sub(r'-part[0-9]+$', '', str(n).replace(BYID, ''))
 gone = lambda n, st: base(n) in lost or str(n).isdigit() or st not in ('ONLINE', 'DEGRADED', '')
 for t in tops:
  if t['section'] in ('cache', 'spares', 'logs'):
   continue
  leaves = t['leaves'] or [(t['name'], t['state'])]
  g = sum(1 for n, st in leaves if gone(n, st))
  if t['name'].startswith(('mirror', 'replacing', 'spare')) and t['leaves']:
   ok = g < len(leaves)
  elif t['name'].startswith(('raidz', 'draid')):
   m = re.match(r'^(?:raidz|draid)([0-9]?)', t['name'])
   ok = g <= int(m.group(1) or '1')
  else:
   ok = g == 0
  if not ok:
   return False
 return True

def holdstate():
 import json
 try:
  with open(HOLDF) as f:
   d = json.load(f)
  return d if isinstance(d, dict) else {}
 except Exception:
  return {}

def holdsave(d):
 import json
 try:
  tmp = HOLDF+'.'+str(os.getpid())
  with open(tmp, 'w') as f:
   json.dump(d, f)
  os.replace(tmp, HOLDF)
 except Exception:
  pass

def holdnum(v):
 try:
  return float(v)
 except Exception:
  return None

def holdentry(pool, host, ready, now=None):
 # (first, notready) of the hold of <pool> for <host>, updated for this pass (r10l K1 / K2, see above).  The same host and
 # a held pass less than HOLDGAP s ago continue the hold; anything else (another host, an old or a round 10k entry
 # without 'last') starts a new one.  notready: None while <host> is ready, else when this hold first saw it not ready.
 d = holdstate()
 e = d.get(pool)
 now = stamp() if now is None else now
 last = holdnum(e.get('last')) if isinstance(e, dict) else None
 first = holdnum(e.get('first')) if isinstance(e, dict) else None
 cont = isinstance(e, dict) and e.get('host') == host and last is not None and first is not None and 0 <= now - last <= HOLDGAP
 if not cont:
  first = now
 nr = None
 if not ready:
  nr = holdnum(e.get('notready')) if cont else None
  if nr is None:
   nr = now
 d = {p: v for p, v in d.items() if isinstance(v, dict) and now - (holdnum(v.get('last', v.get('first'))) or 0) < 86400}
 d[pool] = {'host': host, 'first': first, 'last': now}
 if nr is not None:
  d[pool]['notready'] = nr
 holdsave(d)
 return first, nr

def holdprune(seen):
 # r10l (K1): drop the entries of pools this pass did not judge (no longer asked to import here, taken back, ...)
 d = holdstate()
 k = {p: v for p, v in d.items() if p in seen}
 if len(k) != len(d):
  holdsave(k)

def holdclear(pool):
 d = holdstate()
 if d.pop(pool, None) is not None:
  holdsave(d)

def lostnames(dev):
 # r10n (V-1 / V-13): the names a 'zpool import' listing may give the device <dev>: its by-id base name and, for a /dev
 # node (a scan device without a by-id link) or the node a link points to, 'sdX1' and 'sdX' (round 10m matched the by-id
 # form only: a leg passed as /dev/sdX1 was never counted as lost and a raidz that needed it was imported)
 import re
 names = set([re.sub(r'-part[0-9]+$', '', str(dev).replace(BYID, ''))])
 for p in (str(dev), os.path.realpath(str(dev))):
  if p.startswith('/dev/') and not p.startswith(BYID):
   b = os.path.basename(p)
   names |= set([b, re.sub(r'[0-9]+$', '', b)])
 return names

def leavehold(pool, devs, poolid=''):
 # ('' or the reason to wait, a note for the log when a hold ends): see the r10k comment above
 import re
 HOLDSEEN.add(pool)                       # r10l (K1): judged in this pass, its entry is kept
 byhost = {}
 for d in devs:
  h, st = targetof(d)
  if h and h != myhost:
   byhost.setdefault(h, []).append((d, st))
 for h in sorted(byhost):
  hd = byhost[h]
  lost = set(x for d, st in hd for x in lostnames(d))
  if len(hd) == len(devs):
   need = 'every present member disk ('+str(len(hd))+') is on '+h+"'s target"
  else:
   out = ''
   try:
    out = subprocess.run(['timeout','60','/usr/sbin/zpool','import']+[x for d in devs for x in ('-d', d)],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode('utf-8','replace')
   except Exception:
    pass
   tops = vdevtree(out, pool, poolid if str(poolid).isdigit() else '')
   if tops is None or survives(tops, lost):
    continue
   need = str(len(hd))+' of '+str(len(devs))+' member disks are on '+h+"'s target and "+pool+' cannot run without them'
  rd = get(leaderip, 'ready', '--prefix')
  ready = any(isinstance(x, (list, tuple)) and x and str(x[0]) == 'ready/'+h for x in (rd if isinstance(rd, list) else []))
  now = stamp()
  first, nr = holdentry(pool, h, ready, now)       # r10l (K1, K2)
  age = int(now - first)
  since = 'held since '+strftime('%H:%M:%S', localtime(first))
  bad = sorted(set(st or 'unknown' for d, st in hd if st != 'LOGGED_IN'))
  if bad:
   return 'skipped: '+need+', its iSCSI session is '+'/'.join(bad)+' (the disks are going away); '+since, ''
  if ready and age < HOLDMAX:
   return 'skipped: '+need+' and '+h+' is still ready (leaving: its target goes after the export); '+since+' (at most '+str(HOLDMAX)+' s)', ''
  nrs = 'not ready since '+strftime('%H:%M:%S', localtime(nr)) if nr is not None else ''
  if not ready and now - nr < HOLDMIN:
   return 'skipped: '+need+'; '+h+' is not ready, its target still answers; '+since+', '+nrs+' ('+str(HOLDMIN)+' s)', ''
  return '', 'hold ended after '+str(age)+' s: '+need+', '+h+(' is still ready' if ready else ' is not ready ('+nrs+')')+', its session LOGGED_IN: imported as before'
 holdclear(pool)
 return '', ''

# r10m (QC proof 10l N7, CRITICAL): in r561 zfs2 imported P1 at 17:07:08 by 'zpool import <id>' -- no '-d', no hold --
# 4 s after stopnode had exported it on zfs1, while every member sat on zfs1's target; when zfs1's container went away
# the session failed and P1 was SUSPENDED (17:10:10).  memberdevs() found no device for P1's member names in that second
# (r10n, validator V-15: the cause is not proven -- the by-id links were missing or the names were not resolvable; the
# container has no udev, its links come from cdiskids.sh only), so the import ran with the default scan, which found
# the disks under /dev, and leavehold() got an empty device list (nothing
# to judge: no hold).  Container flavour now: when no member device is found by name, a list-only 'zpool import' (default
# scan) gives the devices of the pool's block (its id, else the only block of its name); leavehold() judges THOSE and
# the import uses '-d <device>' for each of them.  The import never runs without knowing its devices: a pool the scan
# lists but whose devices cannot be found here is not imported (logged), a pool the scan does not list is not tried (N6).
SCANSECTIONS = ('cache', 'spares')
def scandevs(pool, poolid=''):
 # (devices, listed): the devices of <pool>'s present member legs found by a list-only default scan, by-id links where
 # one points to the same device; listed = the scan shows the pool at all
 try:
  out = subprocess.run(['timeout','60','/usr/sbin/zpool','import'], stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL).stdout.decode('utf-8','replace')
 except Exception:
  out = ''
 tops = vdevtree(out, pool, poolid if str(poolid).isdigit() else '')
 if tops is None:
  return [], False
 devs = []
 for t in tops:
  if t['section'] in SCANSECTIONS:
   continue
  for n, st in t.get('devs') or t['leaves'] or [(t['name'], t['state'])]:     # r10n (V-10): nested leaves too
   if str(n).isdigit() or st not in ('ONLINE', 'DEGRADED', ''):
    continue                              # a leg that is missing (guid) or not usable is not a device of this import
   d = devpath(n)
   if d and d not in devs:
    devs.append(d)
 return devs, True

def devpath(name):
 # the device of a vdev name as 'zpool import' prints it (scsi-<wwid> for a whole disk, scsi-<wwid>-part1, sdj1, a path):
 # the by-id link (the -part1 of a whole disk) when one exists, else the /dev node; '' when nothing is found
 name = str(name)
 if name.startswith('/'):
  cands = [name]
 else:
  cands = [BYID+name+'-part1', BYID+name, '/dev/'+name+'1', '/dev/'+name]
 for c in cands:
  if c.endswith('-part9') or not os.path.exists(c):
   continue
  if c.startswith(BYID):
   return c
  real = os.path.realpath(c)
  try:
   links = sorted(os.listdir(BYID), key=lambda x: (not x.startswith('scsi-'), x))
  except OSError:
   links = []
  for l in links:
   if l.startswith(('scsi-', 'wwn-')) and os.path.realpath(BYID+l) == real:
    return BYID+l
  return c
 return ''

# r10m (QC proof 10l N6, LOW): a pool with no member visible (its disks are all on a node that is away) was tried every
# pass ('importing: zpool import <id>' / 'import failed (rc 1) ... no such pool available', 61 lines in 10 min, 30 min
# long).  Now the scan above decides: not listed = no import try, one constant decision line, and the pool is looked at
# again after a growing pause (MISSSTEP s, doubled per miss, at most MISSMAX s).  Container flavour only.
MISSF = '/root/zpooltoimport.miss'
MISSSTEP = 15
MISSMAX = 120
MISSSEEN = set()
def missstate():
 import json
 try:
  with open(MISSF) as f:
   d = json.load(f)
  return d if isinstance(d, dict) else {}
 except Exception:
  return {}

def misssave(d):
 import json
 try:
  tmp = MISSF+'.'+str(os.getpid())
  with open(tmp, 'w') as f:
   json.dump(d, f)
  os.replace(tmp, MISSF)
 except Exception:
  pass

def misswait(pool, now=None):
 # True while the pause after the last miss of <pool> runs (no scan, no import try in this pass)
 MISSSEEN.add(pool)
 e = missstate().get(pool)
 now = stamp() if now is None else now
 try:
  nxt = float(e.get('next', 0)) if isinstance(e, dict) else 0
 except Exception:
  nxt = 0
 return now < nxt and nxt - now <= MISSMAX + 5

def missnote(pool, now=None):
 d = missstate()
 e = d.get(pool) if isinstance(d.get(pool), dict) else {}
 now = stamp() if now is None else now
 try:
  n = int(e.get('n', 0)) + 1
 except Exception:
  n = 1
 wait = min(MISSSTEP * 2 ** (n - 1), MISSMAX)
 d[pool] = {'n': n, 'next': now + wait, 'first': e.get('first', now)}
 misssave(d)
 return wait

def missclear(pool):
 d = missstate()
 if d.pop(pool, None) is not None:
  misssave(d)

def missprune(seen):
 d = missstate()
 k = {p: v for p, v in d.items() if p in seen}
 if len(k) != len(d):
  misssave(k)

def jstate(path):
 import json
 try:
  with open(path) as f:
   d = json.load(f)
  return d if isinstance(d, dict) else {}
 except Exception:
  return {}

def jsave(path, d):
 import json
 try:
  tmp = path+'.'+str(os.getpid())
  with open(tmp, 'w') as f:
   json.dump(d, f)
  os.replace(tmp, path)
 except Exception:
  pass

# r10n (validator 10m V-13, INFO): a scan device with no by-id link is used as its /dev node (/dev/sdX1).  A pool imported
# that way records 'was /dev/sdX1' for a later lost leg (selectspare's online-by-name needs a by-id 'was', N1), and the /dev
# node is one cdiskids.sh made.  cdiskids.sh has just run (V-4), so a missing link is rare: the pass then waits ONE pass
# (>= DEVWAITMIN s) for the link; if it is still missing, the /dev node is used.  State /root/zpooltoimport.devwait.
DEVWAITF = '/root/zpooltoimport.devwait'
DEVWAITMIN = 5
DEVWAITMAX = 600
DEVSEEN = set()
def devwaited(pool, now=None):
 # True when this pool already waited one pass for its by-id links (the /dev nodes may be used now)
 DEVSEEN.add(pool)
 d = jstate(DEVWAITF)
 now = stamp() if now is None else now
 try:
  t = float(d.get(pool))
 except Exception:
  t = None
 if t is not None and DEVWAITMIN <= now - t <= DEVWAITMAX:
  return True
 if t is None or now - t > DEVWAITMAX or now < t:
  d[pool] = now
  jsave(DEVWAITF, d)
 return False

def devwaitprune(seen):
 d = jstate(DEVWAITF)
 k = {p: v for p, v in d.items() if p in seen}
 if len(k) != len(d):
  jsave(DEVWAITF, k)

# r10n (validator 10m V-12, INFO): a marker that putmarker() put on the OTHER address (the one this node did not answer on
# when it put it) was worked off only if that address became this node's etcdip later.  Such puts are kept in
# /root/poouids.other ({pool: [addresses]}) and the retry loop reads those addresses too (only for these pools: no extra
# etcd call in a normal pass); the entry goes when the marker is deleted.
OTHERF = '/root/poouids.other'
def othermarkers():
 # [(pool, ip)] of markers put on another address than this pass's etcdip
 res = []
 for pool, ips in jstate(OTHERF).items():
  for ip in ips if isinstance(ips, list) else []:
   if ip != etcdip:
    res.append((pool, ip))
 return res

def otherforget(pool):
 d = jstate(OTHERF)
 if d.pop(pool, None) is not None:
  jsave(OTHERF, d)

def delmarker(pool):
 # the marker of <pool> deleted on etcdip and on every other address it was put on
 dels(etcdip, 'poouids/'+pool)
 for p, ip in othermarkers():
  if p == pool:
   dels(ip, 'poouids/'+pool)
 otherforget(pool)

# r10m (QC proof 10l N2): the reguid retry marker poouids/<pool> was put to 'etcdip', fixed when the looper started: a node
# that became leader meanwhile answers on the leader address only, the put to its own address was lost, no marker, and the
# pool kept the id its stale leg also has (QSD5.304 hazard).  Container flavour: every pass reads who leads now and uses
# that node's etcd for its markers; the marker put is read back and, if missing, put to the other address too.
def nowetcd():
 try:
  cur = str(get(leaderip, 'leader')[0]).strip()
 except Exception:
  return etcdip
 if cur == myhost:
  return leaderip
 if validpoolname(cur) and cur not in ('_1', 'None'):
  return myhostip
 return etcdip

def putmarker(pool):
 where = []
 for ip in [etcdip] + [x for x in (leaderip, myhostip) if x != etcdip]:
  put(ip, 'poouids/'+pool, myhost)
  try:
   back = str(get(ip, 'poouids/'+pool)[0])
  except Exception:
   back = ''
  where.append(ip+(' ok' if back == myhost else ' not read back ('+back[:40]+')'))
  if back == myhost:
   if ip != etcdip:
    # r10n (V-12): kept, so the retry loop also reads this address
    d = jstate(OTHERF)
    d[pool] = sorted(set((d.get(pool) if isinstance(d.get(pool), list) else []) + [ip]))
    jsave(OTHERF, d)
    where[-1] += ' (another address than '+etcdip+': the retry loop reads it too)'
   break
 try:
  with open('/root/poouids.log','a') as f:
   f.write(str(stamp())+' '+pool+' reguid after the import refused: marker poouids/'+pool+' put on '+', '.join(where)+'\n')
 except Exception:
  pass
 return where

def droplonekeys():
 # r10k (validator 10j G6): a pools/<digits> key (a vdev guid that the round 10i putzpool wrote as a pool) with no
 # poolnxt/<digits> is skipped by selectimport.py and the leader loop for ever but never deleted (only the node named by a
 # poolnxt/<digits> drops both).  The leader deletes such keys (and a lone poolnxt/<digits>) every pass.  A pool name never
 # is digits only (ZFS needs a leading letter); 'pools/dgsinfo' and the like are not touched.
 for prefix in ('pools/', 'poolnxt/'):
  try:
   keys = get(leaderip, prefix, '--prefix')
  except Exception:
   continue
  for kv in keys if isinstance(keys, list) else []:
   k = str(kv[0]) if isinstance(kv, (list, tuple)) and kv else ''
   name = k[len(prefix):] if k.startswith(prefix) else ''
   if name.isdigit():
    dels(leaderip, prefix+name)
    decision('leader:'+name, 'dropped: '+prefix+name+' (a vdev guid, not a pool name)')

def importscan(impdir):
 # r10h (finding 3): the pools 'zpool import -d <impdir>' lists, as [{'name','id','state','members'}]
 # r10j (R1): <impdir> is the import arguments of the pass (container: '-d <device>' per member) or an import dir
 cmd = ['timeout','60','/usr/sbin/zpool','import'] + scanargs(impdir)
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
  if iscontainer() and MEMBERSRC.get(pool) == 'none':
   return None, 'no import by name: etcd lists no member disk of '+pool+' and none was remembered ('+MEMBERF+')'
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
 if iscontainer():
  etcdip = nowetcd()                      # r10m (N2): the etcd this node answers on now
 poouids = get(etcdip,'poouids',myhost)
 nextpools=get(leaderip, 'poolnxt', '--prefix') 
 if 'not reachable' in str(nextpools):
        return
 needtoimport=[ x for x in nextpools if myhost in str(x)] 
 allnow = getall(leaderip)
 pools = [v for k,v in allnow['pools'].items()]
 mypools = [v  for v in pools if v['host'] == myhost ]
 if 'not reachable' in str(pools):
        return
 if iscontainer():
  remembermembers(allnow.get('disks', {}))     # r10i (F2)
 if '_1' in str(poouids):
    poouids = []
 if iscontainer():
    # r10n (V-12): markers put on another address than etcdip (putmarker) are worked off here too
    seenp = set(str(p[0]).split('/')[-1] for p in poouids if isinstance(p, (list, tuple)) and p)
    for opool, oip in othermarkers():
        if opool in seenp:
            continue
        try:
            v = str(get(oip, 'poouids/'+opool)[0])
        except Exception:
            v = '_1'
        if v == myhost:
            poouids.append(('poouids/'+opool, myhost))
            seenp.add(opool)
        elif v == '_1':
            otherforget(opool)             # gone there (deleted by someone else): forget the address
 for poo in poouids:
    print('poouids start')
    pool=poo[0].split('/')[1]
    # Ours is decided by the pool itself (owner property / imported here), not by the pools list of etcd: right after a
    # take over that list still names the old host for a few seconds, the marker was dropped in that window and the pool kept
    # its old id for ever (seen in QC test 14, QSD5.304: the returning node imported its stale leg and the data was lost).
    if not poolishere(pool) or destroyedpool(pool):
        if iscontainer():
            delmarker(pool)                # r10n (V-12): on every address it was put on
        else:
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
            if iscontainer():
                delmarker(pool)            # r10n (V-12)
            else:
                dels(etcdip, 'poouids/'+pool)
        else:
            print('pool not ready yet')
 if iscontainer():
  actpoolreconcile(mypools)      # r10h (finding 5); container flavour only (G8)
 HOLDSEEN.clear()                         # r10l (K1): the pools whose hold this pass judges (leavehold)
 MISSSEEN.clear()                         # r10m (N6): the pools whose missing members this pass looks at
 DEVSEEN.clear()                          # r10n (V-13)
 if myhost not in str(needtoimport):
  print(needtoimport)
  print('no need to import a pool here')
                  
 else:
  for poolline in needtoimport:
   pool = poolline[0].replace('poolnxt/','')
   if iscontainer() and not validpoolname(pool):
    # r10j (R1, putzpool): a vdev guid taken for a pool (pools/<guid>, poolnxt/<guid>): never 'zpool import <guid>'
    decision(pool, 'dropped: not a pool name (a vdev guid), poolnxt/'+pool+' and pools/'+pool+' removed')
    forgetdecision(pool)
    dels(leaderip, 'poolnxt/'+pool)
    dels(leaderip, 'pools/'+pool)
    continue
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
   # r10j (R1): container flavour: '-d /dev/disk/by-id/<disk>-part1' per member, never a /tmp dir (see memberdevs)
   pdisks = getall(leaderip)['disks']
   impargs = importargs(pool, pdisks)
   miss = []
   if iscontainer():
    miss = missingmembers(pool, pdisks)
    if miss and not misswait(pool) and cdiskids():
     # r10n (V-4): a member link is missing: make the links from sysfs now (cdiskids.sh), then look again
     impargs = importargs(pool, pdisks)
     miss = missingmembers(pool, pdisks)
   if iscontainer() and (not impargs or miss):
    # r10m (N7, N6): no member device by name: the devices come from a list-only scan, or nothing is tried
    # r10n (V-1): also when only SOME member disks have no device by name: the scan's devices of the same block are added
    if not impargs and misswait(pool):
     HOLDSEEN.add(pool)                   # a running hold entry is kept while the pause runs
     continue
    sdevs, listed = scandevs(pool, poolid)
    if not impargs and not listed:
     wait = missnote(pool)
     print('import of', pool, 'not tried: no member disk visible, next look in', wait, 's')
     decision(pool, 'waiting: no member disk of '+pool+' is visible (a list-only scan does not show '+str(poolid)+'); not tried, looked at again after a pause ('+str(MISSSTEP)+' s, doubled per miss, at most '+str(MISSMAX)+' s)')
     continue
    if not impargs and not sdevs:
     # r10n (V-11): the same pause as N6 (round 10m ran a new 60 s scan in every pass here)
     wait = missnote(pool)
     decision(pool, 'skipped: a list-only scan shows '+str(poolid)+' but none of its member devices is found here: not imported without knowing its devices; looked at again after a pause ('+str(MISSSTEP)+' s, doubled per miss, at most '+str(MISSMAX)+' s)')
     continue
    missclear(pool)
    named = impargs[1::2]
    added = [d for d in sdevs if not any(samedev(d, x) for x in named)]
    for d in added:
     impargs += ['-d', d]
    if added:
     MEMBERSRC[pool] = ('devices found by a list-only scan' if not named else
                        'devices found by name and by a list-only scan (no device by name for '+' '.join(miss[:4])+')')
   elif iscontainer():
    missclear(pool)
   if iscontainer():
    # r10k (validator 10j G1): never import onto disks that a leaving node's target still serves and the pool cannot lose
    why, note = leavehold(pool, impargs[1::2] if impargs[:1] == ['-d'] else [], poolid)
    if why:
     print('import of', pool, 'held:', why)
     decision(pool, why)
     continue
    nodes = [d for d in impargs[1::2] if not d.startswith(BYID)]
    if nodes and not devwaited(pool):
     # r10n (V-13): one pass for the by-id link of a device the scan found only as a /dev node (judged after the hold)
     decision(pool, 'waiting one pass: '+' '.join(nodes)+' (found by a list-only scan) has no by-id link yet (cdiskids.sh ran); the /dev node is used if the link is still missing in the next pass')
     continue
    if note:
     decision(pool, note)
   cmdline = ' '.join(['/usr/sbin/zpool','import'] + impargs + [poolid])
   # poolnxt/<pool> is the only trigger of this import: it is deleted only after the import worked (below).  It used to be deleted here,
   # before the import, so one failed first try (the disk session of the survivor was not up yet after a take over) orphaned the pool for ever.
   print(cmdline)
   src = MEMBERSRC.get(pool, 'etcd')
   decision(pool, 'importing: '+cmdline+('' if src == 'etcd' or not impargs else ' ('+src+')'))
   put(leaderip, 'pools/'+pool,myhost)
   failnote = ''
   if not iscontainer():
    res = subprocess.run(cmdline.split(),stdout=subprocess.PIPE)      # physical: as before r10h (G8)
   else:
    res = subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   if res.returncode != 0 and iscontainer():
    # r10h (finding 3): why the import failed was thrown away ("import failed (rc 1)" 84 times, nothing else)
    failnote = ': '+res.stderr.decode('utf-8','replace').strip().replace('\n',' | ')[:300]
    alt, why = importbyname(pool, poolid, impargs)
    failnote += '; '+why
    if alt:
     decision(pool, 'import of '+str(poolid)+' failed (rc '+str(res.returncode)+')'+failnote)
     cmdline = ' '.join(['/usr/sbin/zpool','import'] + scanargs(impargs) + [alt])
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
    if iscontainer():
     holdclear(pool)                      # r10k (G1)
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
       if iscontainer():
        delmarker(pool)                   # r10n (V-12)
       else:
        dels(etcdip, 'poouids/'+pool)
    else:
       print('reguid refused (pool not healthy yet), retried later:', result.stderr.decode('utf-8','replace'))
       if iscontainer():
        putmarker(pool)                   # r10m (N2): read back, logged, the other address when lost
       else:
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
 if iscontainer():
  holdprune(HOLDSEEN)                     # r10l (K1): a hold entry lives only while its pool is judged every pass
  missprune(MISSSEEN)                     # r10m (N6)
  devwaitprune(DEVSEEN)                   # r10n (V-13)
        
    
 if myhost != leader:
  return

 readies=get(etcdip,'ready','--prefix')
 hosts=get(leaderip,'host','/current')
 if iscontainer():
  droplonekeys()                          # r10k (validator 10j G6)
 
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
    if iscontainer() and not validpoolname(pool):
     continue      # r10j (R1, putzpool): a vdev guid is never a pool to assign
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
