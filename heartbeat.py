#!/usr/bin/python3

import sys, os, subprocess
from etcdget import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
from time import sleep
from time import time as stamp

leader, leaderip, myhost, myhostip, nextleader, nextleaderip = '','','','','',''
etcd = ''
dev = 'enp0s8'
os.environ['ETCDCTL_API']= '3'


def dosync(*args):
  global etcd, leader ,leaderip, myhost, myhostip, nextleader, nextleaderip
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 




def splitnext(value):
 # nextlead/er is '<host>/<ip>', written by the leader (see leadernextlead).  Older branches wrote the bare
 # host name; a value without a host in it ('None', '_1', '-1') means there is no next leader.
 value = str(value)
 if 'dhcp' not in value:
  return '', ''
 parts = value.split('/')
 return parts[0], (parts[1] if len(parts) > 1 else '')

CLOSTTRIES = 4      # r10o (O3): failed probe rounds before a node is lost, container flavour (physical: 2)
def iscontainer():
 return os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv') or os.path.isdir('/sys/class/net/eth10')

# QSD5.352 r10i (QC proof 10h O3): the leader declared ITSELF lost.  The main loop reads 'ready' from this node's etcd 8 times
# in a row (no pause); when no answer names a node it takes the LEADER for lost -- also when this node IS the leader (its own
# etcd was slow for a few seconds).  zfs1 then ran hostlost.sh for itself: its own disks were deleted from sysfs, closthost.sh
# removed its own iSCSI target (P1 lost its zfs1 leg for 46 s, the optimizer replaced it with a zfs2 disk), exported P1
# ("it can be imported by the node the leader names"), and ready/<itself> was deleted: zfs2 imported P1 and the owner moved
# (00:13:27-00:14:36 node time, 2.5 min after setup).  Container flavour: a node never runs the host-lost path for itself;
# the failed read is logged (at most once a minute, /root/heartproblem) and the next loop reads again.
SELFLOSTLAST = [0.0]
def notmyself(host, why):
 if host != myhost or not iscontainer():
  return False
 if stamp() - SELFLOSTLAST[0] >= 60:
  SELFLOSTLAST[0] = stamp()
  try:
   from datetime import datetime
   with open('/root/heartproblem','a') as f:
    f.write('\n'+datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' '+myhost+' is the leader: '+why+'; not taken for lost (r10i), read again in the next loop\n')
  except Exception:
   pass
 return True

# QSD5.352 r10r2 (QC proof r10r, candidate A: false take-over loop, 3 pools DEGRADED).  Container flavour.
# A follower whose OWN etcd gave no 'ready' node in one pass (8 reads of 2 s under host load 22-36, ~16 s) took the LIVE
# leader for lost without probing it (the 'tries < 10' branch): leaderlost.sh -> docker_primary.sh took the cluster ip,
# hostlost.sh deleted the leader's SCSI devices from the shared kernel, closthost.sh removed its iSCSI target and tried to
# export its pools; 32 take-overs in 90 min.  Now: (1) the own etcd must fail for OWNFAILSECS s and OWNFAILPASSES passes
# in a row, (2) then the leader is probed (hostalive.sh: its node ip, the portal of its target, the cluster ip held
# elsewhere; CLOSTTRIES rounds) and only a leader that does not answer is taken for lost; (3) hostlost() checks every lost
# host once more (one round) before anything is deleted, and leaderlost.sh / hostlost.sh / closthost.sh refuse a host
# that answers (second guards).  The node ip of every host is kept from the last good 'ready' read (NODEIPS).
HOSTALIVE = '/pace/hostalive.sh'
NODEIPS = {}
OWNFAILSECS = 60
OWNFAILPASSES = 3
OWNFAILPAUSE = 5
OWNFAIL = {'first': 0.0, 'passes': 0, 'logged': 0.0}

def hblog(msg):
 try:
  from datetime import datetime
  with open('/root/heartproblem','a') as f:
   f.write('\n'+datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' '+str(myhost)+' '+msg+'\n')
 except Exception:
  pass

def hostanswers(host, rounds=1, cluster=True):
 # ('alive'|'dead'|'unknown', reasons).  The leader is also probed on the cluster ip (skipped by hostalive.sh when the
 # address is on this node itself).  A hostalive.sh that fails or hangs gives 'unknown'.
 # r10r3 (validator r10r2 V-3): cluster=False probes the node ip only (the probe loop has just failed CLOSTTRIES rounds
 # on the cluster ip; probing it again only delays a genuine take-over).
 targets = [NODEIPS.get(host, '-')]
 if cluster and host == leader and str(leaderip):
  targets.append(str(leaderip))
 state, why = 'unknown', []
 for i, ip in enumerate(targets):
  try:
   r = subprocess.run([HOSTALIVE, host, ip, str(etcd) if etcd else '-', str(rounds if i == 0 else 1)],
                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=40 + 10 * rounds)
   rc, out = r.returncode, r.stdout.decode('utf-8', 'replace').strip().replace('\n', ' ')
  except Exception as e:
   rc, out = 3, 'hostalive.sh did not answer: '+str(e)[:80]
  why.append(out)
  if rc == 0 and 'ALIVE' in out:          # its answer line, not only the exit code
   return 'alive', ' | '.join(why)
  if rc == 1:
   state = 'dead'
 return state, ' | '.join(why)

def owntakeover():
 # the 'tries < 10' branch (own etcd gave no ready node): True only when the leader may be taken for lost
 now = stamp()
 if not OWNFAIL['first']:
  OWNFAIL['first'], OWNFAIL['passes'] = now, 0
 OWNFAIL['passes'] += 1
 span = int(now - OWNFAIL['first'])
 if span < OWNFAILSECS or OWNFAIL['passes'] < OWNFAILPASSES:
  if OWNFAIL['passes'] == 1:
   hblog("own etcd at "+str(etcd)+" gave no ready node: no take-over before "+str(OWNFAILSECS)+" s and "+str(OWNFAILPASSES)+" failed passes (r10r2)")
  sleep(OWNFAILPAUSE)
  return False
 state, why = hostanswers(leader, CLOSTTRIES)
 if state == 'dead':
  hblog("own etcd at "+str(etcd)+" gave no ready node for "+str(span)+" s ("+str(OWNFAIL['passes'])+" passes) and the leader "+str(leader)+" does not answer: "+why+"; host-lost path")
  OWNFAIL['first'] = 0.0
  return True
 if now - OWNFAIL['logged'] >= 60:
  OWNFAIL['logged'] = now
  try:
   port = subprocess.run(['timeout', '10', 'docker', 'port', 'etcd'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode('utf-8', 'replace').strip().replace('\n', ', ')
  except Exception:
   port = '?'
  hblog("own etcd unreadable but leader "+str(leader)+" "+('alive' if state == 'alive' else 'not provably lost')+" ("+why+"); no take-over, read again (failed "+str(span)+" s, "+str(OWNFAIL['passes'])+" passes; docker port etcd: "+port+")")
 sleep(OWNFAILPAUSE)
 return False

def getnextlead():
 # read only: a node never announces itself, the leader names the next leader and syncs it to every node
 global etcd, leader ,leaderip, myhost, myhostip, nextleader, nextleaderip
 nextleader, nextleaderip = splitnext(get(etcd,'nextlead/er')[0])
 if nextleader and not nextleaderip:
  nextleaderip = str(get(etcd,'ready/'+nextleader)[0])
 return nextleader , nextleaderip

readyseen = None
# QSD5.352 r10r (QC proof 10q S-2): the leader re-posted the UNCHANGED sync/nextlead/Add_er_<follower>::<ip> item with a
# new stamp every few minutes under load (r10q x1 18:23:35, x2 19:40); each re-post must be acked by the follower (60-85 s
# at load ~20), so isinsync flapped to 'no'.  Two load-made triggers in leadernextlead(): (1) the read of nextlead/er
# failed (etcdget gives '_1' when etcdctl does not answer) so the stored value looked different and was put and posted
# again; (2) one 'ready' read without the follower's record made it a NEW ready node in the next pass (readyseen keeps
# only the last pass).  Container flavour: (1) a failed read skips the pass (a missing key is still written), (2) a node
# is new only when it was not seen for READYGRACE s.  Every post is logged with its reason in NEXTLEADLOG.
READYGRACE = 90
NEXTLEADLOG = '/root/nextlead.log'
readylast = {}

def nlog(msg):
 try:
  with open(NEXTLEADLOG, 'a') as f:
   f.write(str(int(stamp()))+' '+msg+'\n')
 except Exception:
  pass

def readkey(ip, key, tmo=10):
 # (True, value) or (True, '') for a missing key; (False, '') when etcdctl did not answer
 try:
  r = subprocess.run(['timeout', str(tmo), 'etcdctl', '--endpoints=http://'+str(ip)+':2379', 'get', key],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, ETCDCTL_API='3'))
 except Exception:
  return False, ''
 if r.returncode != 0:
  return False, ''
 lines = r.stdout.decode('utf-8', 'replace').split('\n')
 return True, (lines[1].strip() if len(lines) > 1 and lines[0].strip() == key else '')
leadernext = ''        # follower: the last nextlead/er '<host>/<ip>' read from the leader's etcd (see followernextlead)
nextcheck = 0

def followernextlead():
 # FOLLOWER ONLY, every 30 s.  QSD5.352 r10 (QC 680): the follower's own copy of nextlead/er could be '_1' (a return whose
 # sync was never posted, see leadernextlead) while the leader held the right value.  The follower keeps the leader's
 # value in memory and repairs its own copy with it, so a later leader loss finds the next leader.
 global etcd, leaderip, leadernext, nextcheck
 if stamp() < nextcheck:
  return
 nextcheck = stamp() + 30
 followeraliases()      # r10c (B-1)
 value = str(get(leaderip,'nextlead/er')[0])
 host, ip = splitnext(value)
 if not host or not ip:
  return
 leadernext = value
 local = str(get(etcd,'nextlead/er')[0])
 if local != value:
  put(etcd, 'nextlead/er', value)
  with open('/root/heartproblem','a') as f:
   f.write('\nnextlead/er repaired from the leader: '+local+' -> '+value+'\n')

def followeraliases():
 # FOLLOWER ONLY, with followernextlead (every 30 s).  QSD5.352 r10c (QC proof B-1, 525.2/528.2/529.1): the follower's own
 # copies of the node aliases (alias/<host>) went stale: its own alias after a return (docker_setup wrote it to the
 # leader only and marked the sync done for itself) and another node's alias (529.1: after a take-over the new cluster
 # etcd, the follower's old copy, named zfs1 by its host name instead of q529l).  Copy every alias the leader has that
 # differs here.  Only on a good read (a list of ('alias/<host>', value) pairs); an alias the leader does not have is
 # not deleted (a read that missed keys must not remove anything).
 global etcd, leaderip
 theirs = get(leaderip, 'alias', '--prefix')
 if not isinstance(theirs, list) or '_1' in theirs or '-1' in theirs:
  return
 pairs = {}
 for k in theirs:
  if isinstance(k, (list, tuple)) and len(k) == 2 and str(k[0]).startswith('alias/dhcp'):
   pairs[str(k[0])] = str(k[1])
 if not pairs:
  return
 mine = {}
 for k in get(etcd, 'alias', '--prefix'):
  if isinstance(k, (list, tuple)) and len(k) == 2:
   mine[str(k[0])] = str(k[1])
 for key, value in pairs.items():
  if value in ('', '_1', '-1', 'None') or mine.get(key) == value:
   continue
  put(etcd, key, value)
  with open('/root/heartproblem','a') as f:
   f.write('\n'+key+' repaired from the leader: '+str(mine.get(key, 'missing'))+' -> '+value+'\n')

def fallbacknext(losthost):
 # QSD5.352 r10 (QC 680): the leader is lost and this node's nextlead/er names nobody.  Use the leader's last value kept in
 # memory; else the ready nodes this node knows (itself included), the lost leader left out, first by name, so every
 # surviving node picks the same one.  Returns ('', '') when nobody is left.
 host, ip = splitnext(leadernext)
 if host and ip and host != losthost:
  return host, ip, 'leader value kept in memory'
 cands = { myhost: myhostip }
 for k in get(etcd,'ready','--prefix'):
  if isinstance(k, (list, tuple)) and len(k) == 2 and str(k[0]).startswith('ready/'):
   h = str(k[0]).split('/')[1]
   if 'dhcp' in h and h != losthost and h not in cands:
    cands[h] = str(k[1])
 cands.pop(losthost, None)
 if not cands:
  return '', '', 'no ready node'
 host = sorted(cands)[0]
 return host, cands[host], 'first ready node by name'

def nodeevent(code, severity, *params):
 # QSD5.352 (QC 707, 605, 681): the leader announces a node that is ready again (a return or a join: Partsu01 'Node <host>
 # completed joining cluster with ip <ip>') and a lost node that was not the leader (Partst02 'Node <host> is down';
 # leaderlost.sh only sent it when the LEADER was lost).  Only the leader sends them, so every event is logged once.
 try:
  subprocess.run(['docker','exec','etcdclient','/TopStor/logmsg.py',code,severity,'system']+[str(p) for p in params],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
 except Exception as e:
  print('node event', code, params, e)

def leadernextlead(knowns):
 # LEADER ONLY.  The leader names the next leader: a node that has just become ready, or -- when the
 # current one is not a ready node any more (lost, evacuated, this node itself after a take over, None) --
 # another ready node.  It writes nextlead/er = '<host>/<ip>' and posts the sync request (the request and
 # the leader's own done mark), so the checksyncs looper of every node copies it into its local etcd.
 global etcd, leader ,leaderip, myhost, myhostip, readyseen
 others = [ (k[0].split('/')[1], str(k[1])) for k in knowns if 'ready/' in str(k[0]) and k[0].split('/')[1] != myhost ]
 names = [ o[0] for o in others ]
 ctr = iscontainer()
 if ctr:
  now = stamp()
  # r10r (S-2): new = absent in the previous pass AND not seen for READYGRACE s (a node that returns was away for minutes;
  # one read without it is not a return; a slow leader pass > READYGRACE with the node present in every pass is not one either)
  new = [] if readyseen is None else [ o for o in others if o[0] not in readyseen and now - readylast.get(o[0], 0) > READYGRACE ]
  for o in others:
   readylast[o[0]] = now
 else:
  new = [] if readyseen is None else [ o for o in others if o[0] not in readyseen ]
 readyseen = set(names)
 for host, ip in new:
  nodeevent('Partsu01', 'info', host, ip)
 if len(others) == 0:
  return
 if ctr:
  ok, current = readkey(leaderip, 'nextlead/er')
  if not ok:
   print('nextlead/er not readable on', leaderip, 'pass skipped')
   nlog('nextlead/er not readable on '+str(leaderip)+': no post in this pass (new ready nodes '+str([n[0] for n in new])+')')
   if new:
    readyseen = readyseen - set(n[0] for n in new)      # their post is not lost: they stay new for the next pass
    for n in new:
     readylast.pop(n[0], None)
   return
  if current == '':
   current = '_1'                                   # a missing key, as etcdget gave it
 else:
  current = str(get(leaderip,'nextlead/er')[0])
 curhost, curip = splitnext(current)
 if len(new) > 0:
  choice = new[-1]
 elif curhost not in names:
  choice = others[-1]
 else:
  choice = [ o for o in others if o[0] == curhost ][0]
 value = choice[0]+'/'+choice[1]
 # QSD5.352 r10 (QC 680): a node that is ready AGAIN (a return) may be the next leader already: the value did not change,
 # so no sync request was posted and the returned node kept nextlead/er = '_1' in its own etcd (its local copy was not
 # restored).  When the leader was stopped next, that node's heartbeat read '_1', never ran leaderlost.sh and the cluster
 # stayed without a leader.  A newly ready node now always gets the sync request, changed value or not.
 if current == value and len(new) == 0:
  return
 print('next leader is now', value, 'it was', current, 'new ready nodes', [ n[0] for n in new ])
 if ctr:
  nlog('post sync/nextlead/Add_er_'+choice[0]+'::'+choice[1]+': '+('value changed from '+str(current) if current != value else 'same value')+(', new ready nodes '+str([n[0] for n in new]) if new else ''))
 put(leaderip, 'nextlead/er', value)
 dels(leaderip,'sync/nextlead/Add_er','--prefix')
 dosync('sync/nextlead/Add_er_'+choice[0]+'::'+choice[1]+'/request','nextlead_'+str(stamp()))

def hostlost(host, hostip, checked=False):
                global etcd, leader ,leaderip, myhost, myhostip, nextleader, nextleaderip
                if notmyself(host, 'host-lost path asked for this node itself'):
                        return
                ctr = iscontainer()
                if ctr and not checked:
                        # r10r2 (candidate A): one more probe of the host itself before anything is deleted
                        state, why = hostanswers(host, 1, cluster=False)      # r10r3 V-3: node ip only
                        if state == 'alive':
                                hblog(str(host)+' '+str(hostip)+' not taken for lost, it answers: '+why+' (r10r2)')
                                return
                        hblog(str(host)+' '+str(hostip)+' lost, one probe of its node ip: '+state+' ('+why+') (r10r3)')
                oldleader = leader
                with open('/root/heartproblem','a') as f:
                        f.write('nmap:\n'+host+' '+hostip)

                stampit = str(stamp())
                port = myport = '2379'
                # from this node's own etcd: asking the lost leader's etcd only waited 2 s for the timeout and returned nothing
                clusterip = get(etcd,'namespace/mgmtip')[0]
                if host == leader:
                    dels(myhostip, 'pools',host)
                    dels(myhostip, 'vol',host)
                    print('leader lost. nextleader is ',nextleader, 'while my host',myhost)
                    nextleader, nextleaderip =  splitnext(get(etcd,'nextlead/er')[0])
                    # QSD5.352 r10p (QC proof 10o F3, 522.1/.2): a nextlead/er that names the LOST leader itself (the
                    # leader named itself while no other node was ready, or a broken value) made this node write the dead
                    # leader as the new one and wait: no take-over until a later loop (.200 after 184 s, API ~10 min).
                    # Container flavour: such a value counts as 'names nobody' and the fallback picks the next leader.
                    if nextleader == host and iscontainer():
                        with open('/root/heartproblem','a') as f:
                            f.write('\nnextlead/er names the lost leader '+host+' itself; taken as naming nobody (r10p F3)\n')
                        nextleader, nextleaderip = '', ''
                    if not nextleader:
                        nextleader, nextleaderip, why = fallbacknext(host)
                        with open('/root/heartproblem','a') as f:
                            f.write('\nnextlead/er names nobody; next leader by fallback ('+why+'): '+str(nextleader)+' '+str(nextleaderip)+'\n')
                    if nextleader:
                        if not nextleaderip:
                            nextleaderip = myhostip if nextleader == myhost else str(get(etcd,'ready/'+nextleader)[0])
                        leader = nextleader 
                        put(myhostip,'leader',leader)
                    if myhost == nextleader:
                        cmdline='/pace/leaderlost.sh '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+nextleader+' '+nextleaderip+' '+clusterip+' '+host
                        if ctr:
                            # r10r2: the lost leader's node ip (9th) and 'already probed' for leaderlost.sh's own guard
                            cmdline += ' '+NODEIPS.get(host, '-')
                            result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT,env=dict(os.environ, HOSTALIVE_CHECKED=host)).decode('utf-8')
                            if 'TAKEOVER REFUSED' in result or 'TAKEOVER BUSY' in result:
                                hblog('leaderlost.sh did not take over from '+str(host)+': '+' '.join(l for l in result.split('\n') if 'TAKEOVER' in l)[:300]+'; leader stays '+str(oldleader))
                                leader = oldleader
                                put(myhostip,'leader',oldleader)
                                return
                            # r10r2 (F2): the leader key on this node's own etcd (published on the node ip and the cluster ip
                            # by docker_primary.sh now): put and read back; in r10r the put went to an etcd that no longer
                            # answered on the node ip, the key kept the old leader and the next pass took over again
                            okread, val = False, ''
                            for i in range(3):
                                put(myhostip,'leader',leader)
                                okread, val = readkey(myhostip, 'leader')
                                if okread and val == leader:
                                    break
                                sleep(2)
                            hblog('take-over from '+str(host)+': leader key on '+str(myhostip)+' reads '+(repr(val) if okread else 'nothing (no answer)')+(' OK' if okread and val == leader else ' NOT '+str(leader)))
                        else:
                            result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
                        etcd = leaderip
                        dels(leaderip, 'sync/hostdown/'+host,'--prefix')
                        put(leaderip,'sync/hostdown/'+host+'_/request','hostdown_'+stampit)
                        put(leaderip,'sync/hostdown/'+host+'_/request/'+myhost,'hostdown_'+stampit)
                    put(etcd,'refreshdisown/'+myhost,'yes')
                    result='failed'
                    # wait for the cluster ip to answer again, but never for ever: after 5 minutes give up
                    # and go back to the main loop (it used to spin here, without a pause, until a restart)
                    waituntil = stamp() + 300
                    while 'ok' not in str(result):
                        if stamp() > waituntil:
                            print('no leader answers on', leaderip, 'after 5 minutes .... back to the main loop')
                            with open('/root/heartproblem','a') as f:
                                f.write('\nno new leader on '+leaderip+' after 300s\n')
                            break
                        sleep(1)
                        print('chceking new leader')
                        cmdline='nmap --max-rtt-timeout 500ms -n -p '+port+' '+leaderip 
                        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
                        if ('Host is up' or 'open' ) in result:
                            result = (host,'ok')
                        else:
                            result = (host,'lost')
                
                else:
                    dels(leaderip, 'pools',host)
                    if myhost == leader:
                        nodeevent('Partst02', 'warning', host)
                dels(etcd, 'cpuperf/'+host)
                cmdline='/pace/hostlost.sh '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+host
                if ctr:
                    cmdline += ' '+NODEIPS.get(host, '-')        # r10r2: the lost host's node ip for hostlost.sh's guard
                result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
                if ctr and 'HOSTLOST REFUSED' in result:
                    # r10r3 (validator r10r2 V-5): hostlost.sh found the host answering (its own probe, a race with this
                    # one): it deleted nothing, so its ready/running/host/known/vol keys stay too
                    hblog('hostlost.sh refused '+str(host)+': '+' '.join(l for l in result.split('\n') if 'HOSTLOST REFUSED' in l)[:300]+'; its etcd keys are kept')
                    return
                dels(etcd,'ready/',host)
                dels(etcd, 'running/', host)
                dels(etcd, 'host', host)
                dels(etcd, 'known/',host)
                dels(etcd, 'vol',host)
                dels(etcd, 'sync/hostdown',host)

def _readyhost(known):
    # the host of a 'ready/<host>' record ('' when the record has another form)
    try:
        return str(known[0]).split('/')[1]
    except (IndexError, TypeError):
        return ''

def heartbeat(*args):
    global etcd, leader ,leaderip, myhost, myhostip
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
    leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
    leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
    myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
    myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    nochange = 1
    knownsn =  0
    port = myport = '2379'
    if myhost == leader:
        etcd = leaderip
    else:
        etcd = myhostip
    nextleader, nextleaderip = getnextlead()
    while True:
        print('looping')
        sleep(1)
        tries = 0
        while tries < 8:
            knowns = get(etcd, 'ready','--prefix')
            if 'dhcp' in str(knowns):
                tries = 10
                break
            tries +=1
        if iscontainer() and tries == 10:
            # r10r2: node ip of every ready host (hostalive.sh probes it), own-etcd failure count back to 0
            # r10r3 (validator r10r2 V-6): before the one-host check, so a good one-host read resets the count too
            for k in knowns:
                if _readyhost(k) and 'dhcp' in _readyhost(k):
                    NODEIPS[_readyhost(k)] = str(k[1])
            if OWNFAIL['first']:
                hblog('own etcd at '+str(etcd)+' answers again after '+str(int(stamp() - OWNFAIL['first']))+' s ('+str(OWNFAIL['passes'])+' failed passes)')
                OWNFAIL['first'], OWNFAIL['passes'] = 0.0, 0
        # r10r3 (validator r10r2 V-6), container flavour: a FAILED read (etcdget gives ['_1'] on a timeout) is not "one
        # host running": it goes on to the own-etcd window below, so failed passes are counted (before, every second failed
        # pass stopped here and the window could never fill).
        if len(knowns) == knownsn and knownsn == 1 and (tries == 10 or not iscontainer()):
            print('only one host is running..,,will do nothing')
            continue
        knownsn = len(knowns)
        # QSD5.352 r10r (QC proof 10q S-4, x3 522.1/522.2), container flavour: the probe pass handles the FIRST host that
        # does not answer and then starts again, so every stale 'ready/<host>' record of an earlier build (no node behind
        # it) cost one full pass (CLOSTTRIES rounds + hostlost/closthost, 40 s .. 4 min under load) BEFORE the real lost
        # leader: zfs2 18:02-18:08 ran closthost for four old-build hosts and only at 18:08:46 for the stopped leader (UI
        # +12 min).  A follower now probes the leader first; the order of the other hosts is unchanged.
        if iscontainer() and myhost != leader:
            knowns = sorted(knowns, key=lambda k: 0 if _readyhost(k) == leader else 1)
            print('probe order', [_readyhost(k) for k in knowns])
        if tries < 10:
           if notmyself(leader, "its own etcd answered 'ready' without a node 8 times"):
               continue
           if iscontainer():
               # r10r2 (candidate A): failed reads over OWNFAILSECS s, then the leader is probed; a live leader is kept
               if not owntakeover():
                   continue
               hostlost(leader, leaderip, checked=True)
               continue
           hostlost(leader, leaderip)
        elif myhost == leader:
           leadernextlead(knowns)
        else:
           followernextlead()
        for known in knowns:
            host = known[0].split('/')[1]
            if host == myhost:
                continue
            if host == leader:
                hostip = leaderip
            else:
                hostip = known[1]
            print('nmapping')
            result = 'failed'
            tries = 0
            # QSD5.352 r10o (QC proof 10n O3), container flavour: a node is lost only after CLOSTTRIES failed rounds, 2 s apart
            # (~16-20 s), an answered ping counts as an answer, and 'res' is new in every round.  Two rounds 1 s apart (~5 s)
            # were shorter than the bond0 re-activation of a leader that started a share under load: the follower took the
            # cluster ip from a live leader and both led with their own etcd (r10n s2, 16:14 UTC).  Physical: unchanged.
            ctr = iscontainer()
            while tries < (CLOSTTRIES if ctr else 2):
                tries +=1
                if ctr:
                    res = ''
                try:
                    cmdline='nmap --max-rtt-timeout 500ms -n -p '+port+' '+hostip 
                    res=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
                except:
                    result=(host,'doubt')
                if ('Host is up' or 'open' ) in res:
                    result = (host,'ok')
                else:
                    result = (host,'doubt')
                if 'doubt' in str(result):
                    print('ddddddddddddddddddddddddd')
                    cmdline='ping -w 1 '+hostip 
                    print(cmdline)
                    try:
                        subprocess.check_output(cmdline.split())
                        if ctr:
                            result=(host,'ok')      # r10o (O3): the ping answered (it was ignored: lost after 2 rounds anyway)
                    except subprocess.CalledProcessError as e:
                        result=(host,'lost')
                if 'ok' in str(result):
                    break
                sleep(2 if ctr else 1)
            print(result)
            if 'ok' not in str(result):
                with open('/root/heartproblem','a') as f:
                        f.write('OK:\n'+host+' '+res)
                hostlost(host, hostip)
                break
    print(leader ,leaderip, myhost, myhostip)
    return leader ,leaderip, myhost, myhostip

 


if __name__=='__main__':

 print(leader ,leaderip, myhost, myhostip)
 heartbeat(*sys.argv)
