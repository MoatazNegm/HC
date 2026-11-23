#!/usr/bin/python3
import subprocess, sys
import os, atexit, grp
from logqueue import queuethis
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdputnoport import etcdput as putnoport
from etcdput import etcdput as put 
from Evacuatelocal import setall
from etcddel import etcddel as dels
from usersyncall import usersyncall, usrfninit, oneusersync, pulladminhash, followadminhash
from groupsyncall import groupsyncall, grpfninit, onegroupsync, addmissinggroups
from socket import gethostname as hostname
from etcdsync import synckeys
from time import time as timestamp
from etctocron import etctocron 
from collectconfig import collectConfig

dirtydic = { 'pool': 0, 'volume': 0 } 
syncanitem = [ 'getconfig','priv','dirty','hostdown', 'replipart','evacuatehost','Snapperiod', 'cron','UsrChange', 'GrpChange', 'user','group','nextlead','cluip','ipaddr', 'namespace', 'tz','ntp','gw','dns','cf', 'log', 'bond' ]
special1 = [ 'passwd' ]
forReceivers = [ 'user', 'group', 'GrpChange', 'UsrChange' ] + special1
wholeetcd = [ 'etherports','offlinethis','localrun','known','nmspce','gateway','deens','enteepe', 'teezee','ceecee', 'pool','pools', 'needtoreplace','Partnr', 'apikeys', 'Snappreiod','leader', 'running','volumes','ports', 'offlines','diskref', 'ports', 'cachespares']
# QSD5.345: 'destroyedpool' = tombstones of deleted pools (DGdestroyPool), so the import loop of every node, also a later
# leader, never takes a stale copy of a deleted pool again (zpooltoimport.py)
etcdonly = [ 'pooldeleting', 'cleanlost','balancedtype','sizevol', 'ActPool', 'alias', 'hostipsubnet', 'allowedPartners','activepool', 'poolnxt','pools', 'logged','ActivePartners','configured','ready', 'pool', 'destroyedpool']
restartetcd = wholeetcd + etcdonly
replisyncs = ['user','group', 'UsrChange', 'GrpChange']
syncs = etcdonly + syncanitem + special1 + wholeetcd

noinit = [ 'getconfig', 'replipart' , 'evacuatehost','hostdown','namespace' , 'ipaddr','cluip']
##### sync request etcdonly template: sync/Operation/ADD/Del_oper1_oper2_../request Operation_stamp###########
##### sync request syncanitem with bash script: sync/Operation/commandline_oper1_oper2_../request Operation_stamp###########
##### sync request syncanitem with python script: sync/Operation/syncfn_commandline_oper1_oper2_../request Operation_stamp###########
##### synced template for request sync[0]/+node stamp #####################
##### initial sync for known nodes : sync/Operation/initial Operation_stamp #######################
##### synced template for initial sync for known nodes : sync/Operation/initial/node Operation_stamp #######################
##### delete request of same sync if ActivePartners qty reached #######################

def signal_reboot_via_etcd(etcd_endpoint, myhost, reason):
    """
    Write the etcd key that the running rebootmepls.sh watcher is polling
    so it will fire /TopStor/docker_setup.sh reboot (which ends in
    /TopStor/reboot.sh — a container-safe power-cycle analog).

    Do NOT call /TopStor/reboot.sh directly from here: that helper is
    invoked exactly once per cycle by rebootmepls.sh. Writing the etcd
    key is the canonical "I need a reboot" signal in this codebase;
    see syncbonds.sh, Evacuate.py, Evacuatelocal.py for the same
    pattern. Inside this privileged container, /sbin/reboot or
    `systemctl reboot` would reboot the HOST kernel, not just us.
    """
    key = 'rebootme/' + myhost
    try:
        put(etcd_endpoint, key, reason)
        print(f"[checksyncs] signaled reboot via etcd {etcd_endpoint} key={key} value={reason}")
    except Exception as exc:
        print(f"[checksyncs] WARNING: failed to write {key}={reason} to {etcd_endpoint}: {exc}")

software = 'na'
usrchangeretry = 300   # seconds a follower keeps a UsrChange whose group is not there yet (UnixChangeUser exit 3)
def reqorder(item):
 """Order of a pending sync request = the time it was filed, in integer nanoseconds.
 The value of a request is <kind>_<name>_<stamp> (user_usr1_<ns>, group_grp1_<ns>) or <kind>_<stamp> (UsrChange_<ns>,
 GrpChange_<ns>, passwd_<seconds.fraction>) or <kind>_initial_<seconds>.  It used to be sorted by the second field, which is the
 NAME for user_/group_ and the stamp for UsrChange_/GrpChange_: digits sort before letters, so the change of a user's groups was
 always processed before the user was created on the node, found no user ('id' failed) and was dropped (group race, test 22).
 'initial' requests (full copies) go first, then the single changes in the order they were made (UnixAddUser files UsrChange
 10 ns after user)."""
 val = str(item[1])
 if '_initial_' in val:
  return 0
 last = val.split('_')[-1]
 try:
  if '.' in last:
   return int(float(last)*1000000000)
  n = int(last)
 except ValueError:
  return 0
 while 0 < n < 100000000000000000:     # seconds / milliseconds / microseconds -> nanoseconds
  n *= 1000
 return n

def isgroupadd(item):
 """a pending group create: sync/group/UnixAddGroup_<params>/request (a group delete is UnixDelGroup_..., a full copy initial)"""
 key = str(item[0])
 if '/group/' not in key:
  return False
 return 'Add' in key.split('/group/',1)[1].split('/')[0].split('_')[0]

def groupsfirst(reqs):
 """A UsrChange that names a group this node does not have yet exits 3 (UnixChangeUser) and is kept and tried again on every
 pass (usrchangeretry).  When such copies sort before the pending sync/group request that creates the group, every pass ran
 them all first (one full UnixChangeUser each, ~5.5 s on a follower) and reached the group only after them (test 629: 27
 copies, ~150 s per pass, the group's members reached node2 after more than 10 minutes).  The UsrChange requests that sort
 before the last pending group create are moved right after it (their order kept; every other request keeps its place), so
 the group is made first and each copy then finds its groups and runs once.  A UsrChange applies the leader's groups, so the
 end state does not depend on this order (test 620)."""
 last = -1
 for i, item in enumerate(reqs):
  if isgroupadd(item):
   last = i
 if last < 0:
  return reqs
 moved = [ x for x in reqs[:last] if '/UsrChange/' in str(x[0]) ]
 if len(moved) == 0:
  return reqs
 print('UsrChange requests after the group create:', len(moved))
 return [ x for x in reqs[:last+1] if '/UsrChange/' not in str(x[0]) ] + moved + reqs[last+1:]

insyncgrace = 20   # seconds a request may stay without the done mark of a node before the cluster reads "not in sync"

def insync(leaderip, leader):
    """isinsync = no only when a node of the cluster (ready/ or ActivePartners/) has not marked a pending request that is older
    than insyncgrace seconds.  Every existing request used to set "no", also one that every node had already marked done (it
    is removed only by the prune of the NEXT leader pass), and a fresh one that no node could have reached yet: the idle
    cluster files a sync/log request every ~14 s, so single reads flickered "no" (test 671).  A request is done by a node when
    the node has a mark (<request>/<node>) with the request's value, as the follower itself decides (mysyncs).  Stamps more
    than 60 s in the future, or none that can be read, count as old.  Done marks whose request is gone are removed (as
    before, once older than insyncgrace); they do not make the cluster "not in sync"."""
    print('checking in sync -------------------')
    isinsync = 1
    result = get(leaderip,'nodedirty','--prefix')
    if 'dhcp' in str(result):
        isinsync = 0
    if isinsync == 1:
        allsyncs = [ x for x in get(leaderip,'sync','--prefix') if isinstance(x,(tuple,list)) and len(x) == 2 ]
        # sync/cversion requests are no longer handled here; scripts that still post them must not block insync
        allsyncs = [ x for x in allsyncs if 'initial' not in x[0] and 'cversion' not in x[0] ]
        nodes = set()
        for pre in ('ready/', 'ActivePartners/'):
            for x in get(leaderip, pre, '--prefix'):
                if isinstance(x,(tuple,list)) and str(x[0]).startswith(pre) and len(str(x[0])) > len(pre):
                    nodes.add(str(x[0])[len(pre):])
        requests = [ x for x in allsyncs if x[0].endswith('/request') ]
        reqvalues = set([ x[1] for x in requests ])
        done = dict()
        orphans = set()
        for x in allsyncs:
            base, sep, host = x[0].rpartition('/')
            if not base.endswith('/request'):
                continue
            done.setdefault(host, set()).add(x[1])
            if x[1] not in reqvalues:
                orphans.add(x[1])
        now = timestamp()
        for orphan in orphans:
            # only old ones: a script that files the mark before its request (UnixAddUser, UnixAddGroup) must not lose it
            if now - reqorder(('', orphan))/1000000000 < insyncgrace:
                continue
            print('done marks without a request, removed:', orphan)
            dels(leaderip,'sync',orphan)
        for req in requests:
            missing = [ h for h in nodes if req[1] not in done.get(h, set()) ]
            if len(nodes) > 0 and len(missing) == 0:
                continue
            age = now - reqorder(req)/1000000000
            if 0 <= age < insyncgrace or -60 < age < 0:
                print('pending, still in its grace time:', req, 'not marked by', missing)
                continue
            print("some nodes didn't sync completely:", req, 'not marked by', missing if len(nodes) > 0 else 'unknown nodes')
            isinsync = 0
            break
    if isinsync:
        print('the cluster is in sync')
        put(leaderip,'isinsync', 'yes')
    else:
        print('some nodes still syncing')
        put(leaderip,'isinsync', 'no')

def initchecks(leader, leaderip, myhost, myhostip):
    if leader == myhost:
        return leaderip
    else:
        return myhostip

def checksync(hostip='request',*args):
 synctypes[hostip](*args)


def syncinit(leader,leaderip, myhost,myhostip):
 global syncs, syncanitem, forReceivers, etcdonly, allsyncs, noinit
 stamp = int(timestamp() + 3600)
 cinitial = str(get(leaderip, 'sync/','initia'))
 for sync in syncs:
  if 'sync/'+sync  not in cinitial:
    print('found new sync')
    put(leaderip,'sync/'+sync+'/'+'initial/request',sync+'_initial_'+str(stamp)) 
    put(leaderip,'sync/'+sync+'/'+'initial/request/'+myhost,sync+'_initial_'+str(stamp)) 
 return

def doinitsync(leader,leaderip,myhost, myhostip, syncinfo,pullsync='pullavail',pport='',myalias=''):
 global syncs, syncanitem, forReceivers, etcdonly, allsyncs, noinit
 syncleft = syncinfo[0]
 stamp = syncinfo[1]
 sync = syncleft.split('/')[1]
 flag = 1
 if sync in syncanitem and sync not in noinit :
    if 'Snapperiod'in sync:
     print('found etctocron')
     synckeys(leaderip,myhostip, sync,sync)
     etctocron(leaderip)
    if sync in 'group':
     print('syncing all groups')
     grpfninit(leader,leaderip, myhost,myhostip,pport)
     groupsyncall(pullsync)
    if sync in 'user':
     print('syncing all users')
     usrfninit(leader,leaderip, myhost,myhostip,pport)
     usersyncall(pullsync)
     groupsyncall(pullsync)
     #synckeys(leaderip, myhostip, pullsync+'user', 'user')
    if sync in ['tz','ntp','gw','dns']: 
     cmdline='/TopStor/HostManualconfig'+sync.upper()+" "+" ".join([leader, leaderip, myhost, myhostip]) 
     print('cmd',cmdline)
     try:
      result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
     except subprocess.CalledProcessError as e:
      # e.g. HostManualconfigTZ exits 1 when the leader has no zone yet: the rest of the initial sync still runs
      print('HostManualconfig'+sync.upper()+' failed (exit '+str(e.returncode)+'): '+e.output.decode('utf-8','replace'))
      result=''
    if sync == 'priv':
        user=syncleft.split('/')[2]
        synckeys(leaderip, myhostip, 'usersinfo/'+user, 'usersinfo/'+user)
        newinfo = get(myhostip,'usersinfo/'+user)[0]
        oldinfo = get(leaderip, 'usersinfo/'+user)[0]
        if oldinfo != newinfo:
            flag = 0
    if 'bond' in sync:
        synckeys(leaderip, myhostip, sync, sync)
        cmdline = f"/TopStor/syncbonds.sh {leaderip}"        
        result = subprocess.run(cmdline.split(), stderr=subprocess.STDOUT)
        if result.returncode == 10:
            print("Bond config changed. Signaling reboot via etcd for after syncs complete.")
            signal_reboot_via_etcd(leaderip, myhost, 'pls_fromsyncs')
 if sync not in syncs:
  print('there is a sync that is not defined:',sync)
  return 
 if sync in syncs:
  if sync == 'Partnr':
   synckeys(leaderip, myhostip, 'Partner','Partner')
  else:
   if 'pullsync' not in pullsync:
    synckeys(leaderip, myhostip, sync,sync)

 if flag:
    if 'pullsync' not in pullsync:
        put(leaderip,syncleft+'/'+myhost, stamp)
    else:
        putnoport(leaderip,pport,syncleft+'/'+myalias, stamp)
        
 if 'pullsync' not in pullsync:
    synckeys(leaderip,myhostip, syncleft, syncleft)

 return


def syncall(leader,leaderip,myhost, myhostip,pullsync='pullavail'):
 global syncs, syncanitem, forReceivers, etcdonly, allsyncs
 # The requests that are pending NOW are covered by the initial syncs below (those copy the leader's
 # current keys), so they are marked done without being applied.  The list must be taken BEFORE the
 # initial syncs: a request posted while they run (this node's own nextlead announcement at the end of
 # docker_setup.sh, for one) is not covered by a copy that was already made, and marking it done lost it --
 # the node then kept nextlead/er = None and never took over when the leader died.  Such a request now
 # stays pending and the syncrequest looper applies it.
 allrequests = get(leaderip,'sync','--prefix')
 otherrequests = [ x for x in allrequests if '/request/dhcp' not in str(x) and 'initial' not in str(x) ] 

 allinitials = get(leaderip,'sync','initial')
 myinitials = [ x for x in allinitials if 'initial' in str(x)  and '/request/dhcp' not in str(x) ] 
 for syncinfo in myinitials:
   doinitsync(leader,leaderip,myhost,myhostip, syncinfo,pullsync)

 # test 14 step 13: ActPool has no initial sync, yet its pending Add requests are marked done below without being applied.
 # A pool created while this node was down therefore never got ActPool/<pool> here; when this node took over, the import
 # was refused ("no ActPool") and diskguard saw the pool's surviving disk as free and gave it to another pool (data lost).
 # The leader's ActPool keys are the truth: copy them, as an initial sync would.
 if myhost != leader and 'pullsync' not in pullsync:
   leaderact = get(leaderip, 'ActPool', '--prefix')
   if leaderact and '_1' not in str(leaderact):
     for item in leaderact:
       if isinstance(item, (tuple, list)) and len(item) > 1 and str(item[0]).startswith('ActPool/'):
         put(myhostip, item[0], item[1])

 for done in otherrequests:
      put(leaderip,done[0]+'/'+myhost,done[1])
      synckeys(leaderip,myhostip, done[0], done[0]) 


 return
def replisyncrequest(replirev, leader,leaderip,myhost, myhostip):
 global syncs, syncanitem, forReceivers, etcdonly,  allsyncs
 print('***************************************************************************')
 print('syncing replication data')
 print(replirev, leader,leaderip,myhost, myhostip)
 print('***************************************************************************')
 flag=1
 pport = replirev[1]
 print('bug',pport)
 grpfninit(leader,leaderip, myhost,myhostip,pport)
 usrfninit(leader,leaderip, myhost,myhostip,pport)
 myalias = replirev[0].split('/')[-2]
 allsyncs = getnoport(leaderip,pport,'sync','request') 
 newallsyncs = []
 for sync in allsyncs:
     for forr in forReceivers:
         if '/'+forr+'/' in sync[0]:
             newallsyncs.append(sync)
 donerequests = [ x for x in newallsyncs if '/request/dhcp' in str(x) ] 
 mysyncs = [ x[1] for x in newallsyncs if '/request/dhcp'+myalias in str(x) or '/request/'+myalias in str(x)] 
 if myhost == leader:
     etcdip = leaderip
     myrequests = [ x for x in newallsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] ] 
 else:
    etcdip = myhostip
    myrequests = [ x for x in newallsyncs if x[1] not in mysyncs  and '/request/'+leader in x[0] ] 
 if len(myrequests) > 1:
     myrequests.sort(key=reqorder, reverse=False)
 
 print('myrequests are', myrequests)
 passstart = __import__('time').time()
 for syncinfo in myrequests:
  # test 679 step 5: the list is read once per pass; a long log back-fill (sorted last) is cut after 60 s so that the next
  # pass reads the list again and a request filed meanwhile (a new group) is not kept waiting behind it
  if '/log/' in str(syncinfo[0]) and __import__('time').time() - passstart > 60:
   print('log back-fill continues in the next pass')
   break
  evacuateflag = 0
  flag = 1
  if  len(syncinfo[0]) == 1:
    continue
  if '/initial/' in str(syncinfo):
   print(leader,leaderip,myhost,myhostip, syncinfo)
   doinitsync(leader,leaderip,myhost,myhostip, syncinfo,'pullsync',pport,myalias)
   continue
  else:
   syncleft = syncinfo[0]
   stamp = syncinfo[1]
   sync = syncleft.split('/')[1]
   opers= syncleft.split('/')[2].split('_')
   print('#########################################################################')
   print('the sync',sync)
   # 'passwd' is handled below by pulladminhash + UnixChangePass; synckeysnoport (etcdsyncnoport.py) is unfinished (undefined 'noport',
   # ignores the tunnel port) and was never imported here, so the NameError ended the whole pull for every password change
   if sync in wholeetcd :
    if sync == 'Partnr':
      print('iam here')
      synckeysnoport(leaderip, pport, leaderip, 'Partner', 'Partner')
    else:
      print('or here')
      synckeysnoport(leaderip, pport, leaderip, sync,sync)
   if sync in etcdonly and myhost != leader:
     if opers[0] == 'Add':
      if 'Split' in opers[1]:
       put(myhostip,sync,opers[2].replace(':::','_').replace('::','/'))
      else:
       print('oper', opers, sync)
       put(myhostip,sync+'/'+opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
     else:
      print(sync,opers)
      if 'ready' not in sync:
        dels(myhostip,opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
      # test 678 step 3: a deleted pool left ActPool/<pool> and sizevol/<pool>/... in the followers' etcd: the ActPool Del
      # request (Del_<pool>_<guid>) deleted the key '<pool>' above, and nothing deleted sizevol.  With the pool, they go.
      if sync == 'pools' and len(opers) > 2:
        dpool = opers[2].replace(':::','_').replace('::','/')
        dels(myhostip, 'ActPool/'+dpool)
        dels(myhostip, 'sizevol/'+dpool, '--prefix')
      if sync == 'ActPool' and len(opers) > 1:
        dels(myhostip, 'ActPool/'+opers[1].replace(':::','_').replace('::','/'))
   if sync in syncanitem:
      if 'nextlead' in sync:
        synckeys(leaderip,myhostip, sync,sync)
        if myhost in str(get(myhostip,'nextlead','--prefix')):
            cmdline='/TopStor/promrepli.sh '+leaderip+' '+myhostip
            result=subprocess.run(cmdline.split(),stderr=subprocess.STDOUT)
      elif 'getconfig' in sync:
        collectConfig(leaderip, myhost)
      elif sync in 'Snapperiod' :
       synckeys(leaderip,myhostip, sync,sync)
       etctocron(leaderip)
      elif sync in 'diskref':
        #cmdline='/pace/diskchange.sh '+' checksync'+' '+opers[0]+' '+opers[1]
        print('diskref',cmdline)
        #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'hostdown':
        cmdline='/pace/hostdown.sh '+opers[0]
        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'dirty':
        for dirt in dirtydic:
            put(etcdip, 'dirty/'+dirt, str(dirtydic[dirt]))
      elif 'syncfn' in opers[0]:
        print('opers_syncfn',opers)
        if 'evacuatehost' in str(syncleft):
            isready = get(etcdip, 'ready',opers[2])
            evacuateflag = 1
            if opers[2] not in str(isready):    
                globals()[opers[1]](*opers[2:])
                dels(etcdip, 'ActivePartners',opers[2])
                if myhost == leader:
                    cmdline = '/TopStor/promserver.sh '+leaderip
                    subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
                    dels(leaderip,'reboot', opers[2])
                    dels(leaderip,'bybyleader',opers[2])
                    discip = '10.11.11.253'
                    put(leaderip, 'excepts/'+opers[2],opers[2])
                    put(discip, 'excepts/'+opers[2],opers[2])
                    dels(discip,'possible', opers[2])
                    dels(leaderip,'possible', opers[2])
                evacuateflag = 0 

        else:        
            globals()[opers[1]](*opers[2:])
      elif sync == 'priv':
        user=syncleft.split('/')[2]
        synckeys(leaderip, myhostip, 'usersinfo/'+user, 'usersinfo/'+user)
        newinfo = get(myhostip,'usersinfo/'+user)[0]
        oldinfo = get(leaderip, 'usersinfo/'+user)[0]
        if oldinfo != newinfo:
            flag = 0
 
      else:
       print('opers_else',opers)
       if sync in ['cluip','ipaddr', 'namespace','tz','ntp','gw','dns', 'cf']: 
        cmdline='/TopStor/HostManualconfig'+sync.upper()+" "+" ".join([leader, leaderip, myhost, myhostip]) 
        print('cmdline',cmdline)
        try:
         result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as e:
         print('HostManualconfig'+sync.upper()+' failed (exit '+str(e.returncode)+'): '+e.output.decode('utf-8','replace'))
         result=''
       elif sync in ['UsrChange', 'GrpChange']:
        cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:-1])+' '+'pullsync'
        print('cmdline',cmdline)
        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
       else:
        print(opers,sync)
        if 'Add' in opers[0]:
            if 'user' in sync:
               print('____________________________________________________________________________________________________________')
               oneusersync('Add',opers[2],'pullsync') 
               print('____________________________________________________________________________________________________________')
            else:
               onegroupsync('Add',opers[2],'pullsync') 
        elif 'Del' in opers[0]:
            if 'user' in sync:
               oneusersync('Del',opers[2],'pullsync') 
            else:
               onegroupsync('Del',opers[2],'pullsync') 
        else:    #'UnixChange' in opers[0]:
            cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:]) 
            print('cmdline',cmdline)
            try:
             result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
            except (FileNotFoundError, PermissionError) as e:
             # an unknown request (no such script) must not crash the loop: it blocked every later request, so a group or
             # user deleted on the leader stayed on the follower
             print('sync request skipped, no such script:', cmdline, e)
   if sync in special1 :
      try:
       pulladminhash(opers[1])   # the receiver must hold the sender's new hash before UnixChangePass reads it from etcd
       cmdline='/TopStor/'+opers[0]+' '+opers[1]+' '+opers[2]
       print('replipass',cmdline)
       result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      except:
       print('in case of admin change, the reuslt is not that ok')
      #cmdline='/TopStor/'+opers[0].split(':')[1]+' '+result+' '+opers[2] +' '+ opers[3]
      #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
   if sync not in syncs:
    # skip it, never stop: a 'return' here dropped every later request on every pass.  A node that came
    # back after a fail over met an old sync/cversion request first (not handled here any more) and so
    # never applied anything again -- stale nextlead/er, cluster never in sync.
    print('there is a sync that is not defined:',sync)
    continue
   if flag == 1 and evacuateflag == 0:
    print(';;;;;;;;;;;;;;;;;;;;updating the remote leader')
    putnoport(leaderip,pport,syncleft+'/dhcp'+myalias, stamp)
 return     



glogfile = '/TopStordata/TopStorglobal.log'
glogrows = None      # the rows of the local log file (without the trailing write time), read once per pass

def writelogrow(a):
 """Append one log row the way /TopStor/logmsg2.sh writes it (date time host type user code@@@args... epoch), once.
 Test 679 step 5: one logmsg2.sh run per copied row (a shell, awk per field, a grep of the whole file) made a returning
 node's first pass take ~35 min, and a group created meanwhile reached it after 485 s.  The file is read once per pass."""
 global glogrows
 dt, tm, host, code, mtype, muser = a[0], a[1], a[2], a[3], a[4], a[5]
 row = dt+' '+tm+' '+host+' '+mtype+' '+muser+' '+code+'@@'+''.join('@'+x for x in a[6:])
 if glogrows is None:
  glogrows = set()
  try:
   with open(glogfile) as f:
    for line in f:
     glogrows.add(line.rstrip(chr(10)).rsplit(' ', 1)[0])
  except OSError:
   pass
 if row in glogrows:
  return
 import time as _t
 with open(glogfile, 'a') as f:
  f.write(row+' '+str(int(_t.time()))+chr(10))
 glogrows.add(row)

def synclogcopy(leaderip, etcdip, logid):
 """In process what /TopStor/synclogs.sh did for one sync/log request (bash + etcdget.py + etcdput.py + etcddel.py, three
 python starts, ~1-3 s on a slow node for every notification of the cluster; a burst files several per object, test 671):
 the leader's log/<logid> into this node's etcd, then this node's own mark key of the request is removed, as there."""
 logdata = str(get(leaderip, 'log/'+logid)[0])
 if logdata in ('', '_1'):
  print('no log data found for log/'+logid+' on the leader', leaderip)
  return
 if etcdip != leaderip:
  put(etcdip, 'log/'+logid, logdata)
  # test 677 step 5: rows written while this node was down never reached its /TopStordata/TopStorglobal.log (they are sent
  # live only to the nodes that are up), so they were gone after the next leader change.  Catching up on the pending
  # sync/log requests now also writes the row into the local file (the value is the logmsg2.sh command line; logmsg2.sh
  # skips a row that is already there).
  args = logdata.split()
  if args and args[0] == '/TopStor/logmsg2.sh' and len(args) >= 7:
   try:
    writelogrow(args[1:])
   except Exception as e:
    print('could not write log/'+logid+' to the local log file:', e)
 dels(etcdip, 'sync/log/'+logid+'/request/'+hostname())
 print('synced log/'+logid, 'from', leaderip, 'to', etcdip)

def samerow(leaderip, myhostip, key):
 """the value of key is the same (and real) in the leader's etcd and in this node's etcd"""
 try:
  lval = str(get(leaderip, key)[0])
  return lval not in ('', '_1', '-1', 'None') and lval == str(get(myhostip, key)[0])
 except Exception:
  return False

def syncrequest(leader,leaderip,myhost, myhostip,pullsync='pullavail'):
 global syncs, syncanitem, forReceivers, etcdonly,  allsyncs
 global glogrows
 glogrows = None          # the local log file is read again in every pass (writelogrow)
 # test 671: the users and groups copied in THIS pass. Their copy read the leader's state after every request of this pass
 # was filed (the list is read first), so their UsrChange / GrpChange / passwd requests of this pass are already applied:
 # marked done without running UnixChangeUser / UnixChangeGroup / UnixChangePass again (one full script each, ~5-25 s per
 # object on the slow follower).
 addedusers = set()
 addedgroups = set()
 #if 'pullsync' in pullsync:
 #   print('***************************************************************************')
 #   print('syncing replication data')
 #   print('***************************************************************************')
 flag=1
 clusterhost = myhost
 if leader == myhost:
    etcdip = leaderip
    if 'pullsync' in pullsync:
        clusterhost = leaderip
 else:
    etcdip = myhostip
    if 'pullsync' not in pullsync:
        followadminhash(leaderip, myhostip)
 allsyncs = get(leaderip,'sync','request') 
 # only real request keys (.../request or .../request/<host>): an entry whose key lost its '/request' (a value with a newline
 # shifted the key/value pairs, test 674 step 7) was marked done as '<key>/<host>' = '/request', which matched again: the
 # marks grew without end (thousands of sync/Partnr keys)
 allsyncs = [ x for x in allsyncs if isinstance(x,(tuple,list)) and len(x) > 1 and '/request' in str(x[0]) ]
 if 'pullsync' in pullsync:
    print('allsyncs',pullsync,allsyncs)
 donerequests = [ x for x in allsyncs if '/request/dhcp' in str(x) ] 
 #mysyncs = [ x[1] for x in allsyncs if '/request/'+myhost in str(x) or ('request/' and '/'+clusterhost) in str(x) ] 
 mysyncs = [ x[1] for x in allsyncs if '/request/'+myhost in str(x) ] 
 print('mysyncs',mysyncs)
 if myhost == leader:
    if 'pullsync' in pullsync:
        myrequests = [ x for x in allsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] ] 
    else:
        myrequests = [ x for x in allsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] and '/initial' not in x[0] ] 
 else:
    myrequests = [ x for x in allsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] ] 
    print('myrequests:',myrequests)
    print('iiiiiiiiiiiiiiiiiiiiiiiiiihere')
 if len(myrequests) > 1:
    print('multiple requests',myrequests)
    myrequests.sort(key=reqorder, reverse=False)
    myrequests = groupsfirst(myrequests)
 # test 679 step 5: log copies (informational) after every other request: a returning node replayed hundreds of them
 # first, and a group created meanwhile waited behind them for minutes
 myrequests = [ x for x in myrequests if '/log/' not in str(x[0]) ] + [ x for x in myrequests if '/log/' in str(x[0]) ]
 print('myrequests are', myrequests)
 passstart = __import__('time').time()
 for syncinfo in myrequests:
  # test 679 step 5: the list is read once per pass; a long log back-fill (sorted last) is cut after 60 s so that the next
  # pass reads the list again and a request filed meanwhile (a new group) is not kept waiting behind it
  if '/log/' in str(syncinfo[0]) and __import__('time').time() - passstart > 60:
   print('log back-fill continues in the next pass')
   break
  evacuateflag = 0
  flag = 1
  if  len(syncinfo[0]) == 1:
    continue
  if '/initial/' in str(syncinfo):
   if myhost != leader or 'pullsync' in pullsync:
    print(leader,leaderip,myhost,myhostip, syncinfo)
    doinitsync(leader,leaderip,myhost,myhostip, syncinfo,pullsync)
   elif myhost == leader:
    syncinit(leader,leaderip, myhost,myhostip)
  else:
   syncleft = syncinfo[0]
   stamp = syncinfo[1]
   print('syncleft',syncleft)
   if 'pullsync' in pullsync:
    syncleft = syncleft.replace(pullsync,'')
   sync = syncleft.split('/')[1]
   opers= syncleft.split('/')[2].split('_')
   print('#########################################################################')
   print('the sync',sync)
   if sync in wholeetcd :
    if sync == 'Partnr':
      synckeys(leaderip, myhostip, 'Partner', 'Partner')
    else:
        synckeys(leaderip,myhostip, sync,sync)
   if sync in etcdonly and myhost != leader:
     if opers[0] == 'Add':
      if 'Split' in opers[1]:
       put(myhostip,sync,opers[2].replace(':::','_').replace('::','/'))
      else:
       print('oper', opers, sync)
       put(myhostip,sync+'/'+opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
     else:
      print(sync,opers)
      if 'ready' not in sync:
        dels(myhostip,opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
      # test 678 step 3: a deleted pool left ActPool/<pool> and sizevol/<pool>/... in the followers' etcd: the ActPool Del
      # request (Del_<pool>_<guid>) deleted the key '<pool>' above, and nothing deleted sizevol.  With the pool, they go.
      if sync == 'pools' and len(opers) > 2:
        dpool = opers[2].replace(':::','_').replace('::','/')
        dels(myhostip, 'ActPool/'+dpool)
        dels(myhostip, 'sizevol/'+dpool, '--prefix')
      if sync == 'ActPool' and len(opers) > 1:
        dels(myhostip, 'ActPool/'+opers[1].replace(':::','_').replace('::','/'))
   if sync in syncanitem:
      if 'nextlead' in sync:
        synckeys(leaderip,myhostip, sync,sync)
        if myhost in str(get(myhostip,'nextlead','--prefix')):
            cmdline='/TopStor/promrepli.sh '+leaderip+' '+myhostip
            result=subprocess.run(cmdline.split(),stderr=subprocess.STDOUT)
      elif 'log' in sync:
        logid=opers[0]+"_"+opers[1]
        try:
          synclogcopy(leaderip, etcdip, logid)
        except Exception as e:
          print('log copy failed', logid, e)
      elif 'bond' in sync:
        synckeys(leaderip, myhostip, sync, sync)
        cmdline ="/TopStor/syncbonds.sh "+etcdip
        result = subprocess.run(cmdline.split(), stderr=subprocess.STDOUT)
        if result.returncode == 10:
            print("Bond config changed. Signaling reboot via etcd for after syncs complete.")
            signal_reboot_via_etcd(etcdip, myhost, 'pls_fromsyncs')
      elif 'getconfig' in sync:
        collectConfig(leaderip, myhost)
      elif sync in 'Snapperiod' :
       synckeys(leaderip,myhostip, sync,sync)
       etctocron(leaderip)
      elif sync in 'diskref':
        #cmdline='/pace/diskchange.sh '+' checksync'+' '+opers[0]+' '+opers[1]
        print('diskref',cmdline)
        #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'hostdown':
        cmdline='/pace/hostdown.sh '+opers[0]
        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'dirty':
        for dirt in dirtydic:
            put(etcdip, 'dirty/'+dirt, str(dirtydic[dirt]))
      elif 'syncfn' in opers[0]:
        print('opers',opers)
        if 'evacuatehost' in str(syncleft):
            isready = get(etcdip, 'ready',opers[2])
            evacuateflag = 1
            if opers[2] not in str(isready):    
                globals()[opers[1]](*opers[2:])
                dels(etcdip, 'ActivePartners',opers[2])
                if myhost == leader:
                    cmdline = '/TopStor/promserver.sh '+leaderip
                    subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
                    dels(leaderip,'reboot', opers[2])
                    dels(leaderip,'bybyleader',opers[2])
                    discip = '10.11.11.253'
                    put(leaderip, 'excepts/'+opers[2],opers[2])
                    put(discip, 'excepts/'+opers[2],opers[2])
                    dels(discip,'possible', opers[2])
                    dels(leaderip,'possible', opers[2])
                evacuateflag = 0 

        else:        
            globals()[opers[1]](*opers[2:])
      elif sync == 'priv':
        user=syncleft.split('/')[2]
        synckeys(leaderip, myhostip, 'usersinfo/'+user, 'usersinfo/'+user)
        newinfo = get(myhostip,'usersinfo/'+user)[0]
        oldinfo = get(leaderip, 'usersinfo/'+user)[0]
        if oldinfo != newinfo:
            flag = 0
 
      else:
       print('opers',opers)
       if sync in ['cluip','ipaddr', 'namespace','tz','ntp','gw','dns', 'cf']: 
        cmdline='/TopStor/HostManualconfig'+sync.upper()+" "+" ".join([leader, leaderip, myhost, myhostip]) 
        print('cmdline',cmdline)
        try:
         result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as e:
         print('HostManualconfig'+sync.upper()+' failed (exit '+str(e.returncode)+'): '+e.output.decode('utf-8','replace'))
         result=''
       elif sync == 'UsrChange' and myhost != leader and len(opers) > 2 and opers[2] in addedusers and not os.path.exists('/tmp/usrchangemissing.'+opers[2]):
        print('UsrChange of', opers[2], 'applied by its user copy in this pass, done')
       elif sync == 'GrpChange' and myhost != leader and len(opers) > 2 and opers[2] in addedgroups and not os.path.exists('/tmp/grpchangemissing.'+opers[2]):
        print('GrpChange of', opers[2], 'applied by its group copy in this pass, done')
       elif sync in ['UsrChange', 'GrpChange']:
        cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:-1])+' '+'pullsync'
        print('cmdline',cmdline)
        try:
         result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as e:
         # exit 3 of UnixChangeUser: a group of the user is not on this node yet (its sync/group request is filed after the
         # UsrChange or comes later in this pass, test 620). The groups that exist were applied; the request is kept and tried
         # again on the next pass, for at most usrchangeretry seconds after it was filed (then the group's own sync applies it).
         if e.returncode == 3 and timestamp() - reqorder(syncinfo)/1000000000 < usrchangeretry:
          print('kept for the next pass:', e.output.decode('utf-8','replace')[-300:])
          flag = 0
         elif e.returncode == 3:
          print('a group is still missing after', usrchangeretry, 's, done:', e.output.decode('utf-8','replace')[-300:])
         else:
          raise
       else:
        print(opers,sync)
        if 'Add' in opers[0]:
            if 'user' in sync:
               # a copy that failed (read from the leader, UnixAddUser) keeps the request: tried again on the next pass
               # (test 619 step 1: marked done without the user)
               added = oneusersync('Add',opers[2],'pullavail')
               if added is False:
                  flag = 0
               elif added is True:
                  addedusers.add(opers[2])
            else:
               onegroupsync('Add',opers[2],'pullavail') 
               # made here and its row is the leader's row now (UnixChangeGroup copies it): its GrpChange of this pass is applied
               try:
                  grp.getgrnam(opers[2])
                  if myhost != leader and samerow(leaderip, myhostip, 'usersigroup/'+opers[2]):
                     addedgroups.add(opers[2])
               except KeyError:
                  pass
        elif 'Del' in opers[0]:
            if 'user' in sync:
               oneusersync('Del',opers[2],'pullavail') 
            else:
               onegroupsync('Del',opers[2],'pullavail') 
        else:    
            cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:]) 
            print('cmdline',cmdline)
            try:
             result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
            except (FileNotFoundError, PermissionError) as e:
             # an unknown request (no such script) must not crash the loop: it blocked every later request, so a group or
             # user deleted on the leader stayed on the follower
             print('sync request skipped, no such script:', cmdline, e)

   #if sync in special1 and myhost != leader :

   if sync in special1 and myhost != leader and len(opers) > 1 and opers[1] in addedusers and samerow(leaderip, myhostip, 'usershash/'+opers[1]):
      # the user was made in this pass with the leader's hash as it is now (UnixAddUser stores it unchanged): applied
      print('passwd of', opers[1], 'applied by its user copy in this pass, done')
   elif sync in special1 :
      try:
       if myhost != leader:
        # UnixChangePass reads the hash from THIS node's etcd; nothing copied the leader's new hash here, so a
        # follower kept (and after a fail over the cluster went back to) the old password
        newhash = str(get(leaderip,'usershash/'+opers[1])[0]).replace('\n','')
        if newhash not in ('_1','-1','','None') and len(newhash) > 3:
         put(myhostip,'usershash/'+opers[1],newhash)
       cmdline='/TopStor/'+opers[0]+' '+opers[1]+' '+opers[2]
       result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      except:
       print('in case of admin change, the reuslt is not that ok')
      #cmdline='/TopStor/'+opers[0].split(':')[1]+' '+result+' '+opers[2] +' '+ opers[3]
      #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
   if sync not in syncs:
    # skip it, never stop: a 'return' here dropped every later request on every pass.  A node that came
    # back after a fail over met an old sync/cversion request first (not handled here any more) and so
    # never applied anything again -- stale nextlead/er, cluster never in sync.
    print('there is a sync that is not defined:',sync)
    continue
   if flag == 1 and evacuateflag == 0:
    if 'sync' in pullsync:
        put(leaderip,pullsync+syncleft+'/'+myhost, stamp)
    else:
        put(leaderip,syncleft+'/'+myhost, stamp)
   if myhost != leader and flag == 1 and evacuateflag == 0:
    print(';;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;')
    put(myhostip, syncleft+'/'+myhost, stamp)
    put(myhostip, syncleft, stamp)
   if myhost == leader  and flag == 1 and evacuateflag == 0:
    print('2;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;')
    put(myhostip, syncleft+'/'+myhost, stamp)
     
 if myhost != leader and 'pullsync' not in pullsync:
  # QSD5.352 fix17 (QC 628): re-add the groups this member missed (a lost or wrongly finished add request)
  try:
   addmissinggroups()
  except Exception as e:
   print('addmissinggroups:', e)
 if myhost != leader:
  dones = get(leaderip,'sync','/request/dhcp')
  otherdones = [ x for x in dones if '/request/dhcp' in str(x) ] 
  localdones = get(myhostip, 'sync', '--prefix')
  for done in otherdones:
   if str(done) not in str(localdones):
    put(myhostip, done[0],done[1])
    put(myhostip, '/'.join(done[0].split('/')[:-1]), done[1])
  deleted = set()
  for done in localdones:
   if done[1] not in str(otherdones) and done[1] not in deleted :
    dels(myhostip, 'sync', done[1])
    deleted.add(done[1])
  print('hihihihi-----------------------------------------')
  print(set(get(myhostip,'sync','UsrChange')+['hi'])-set(get(leaderip,'sync','UsrChange')))
  print('hihihihi-----------------------------------------')
 else:
  actives = len(get(leaderip,'ActivePartners','--prefix')) 
  receivers = get(leaderip,'Partner','Receiver') 
  if '_1' == receivers[0]:
    receivers = 0
  else:
    receivers = len(receivers)
  readis = len(get(leaderip,'ready','--prefix')) 
  readisonly = ('leader','next','ActivePartners', 'alias','nextlead', 'hostdown','pool','volume', '/dirty', 'running','/ready/', 'diskref', '/add')
  print('pruuuuuuuuuuuuuuuuuuuuuning')
  print('receiver',get(leaderip,'Partner','Receiver'))
  toprune = [ x for x in allsyncs if 'initial' not in x[0] ]
  dhcps = [x[1] for x in allsyncs if 'request/dhcp' in x[0] ]
  requests = [ x[1] for x in allsyncs if 'request/dhcp' not in x[0] ]
  notrights = [ x for x in dhcps if x not in requests ]
  toprunedic = dict()
  for prune in toprune:
   if prune[1] not in toprunedic and 'request' in prune[0]:
    toprunedic[prune[1]] = [1,prune[0]]
   else:
    if 'request' in prune[0]:
        toprunedic[prune[1]][0] += 1
        toprunedic[prune[1]].append(prune[0])
  for prune in toprunedic:
   isinreadis = [ x for x in readisonly if x in str(toprunedic[prune][1:]) ]
   if prune.split('_')[0] in forReceivers:
    totalactives = actives + receivers
    totalreadis = readis + receivers
   else:
    totalactives = actives
    totalreadis = readis
   if toprunedic[prune][0] > totalactives or ( len(isinreadis) > 0 and toprunedic[prune][0] > totalreadis):
    if 'initial' not in prune:
        dels(leaderip,'sync',prune) 
  replirevs = get(leaderip,'replirev','--prefix')
  print(replirevs)
  for replirev in replirevs:
     replisyncrequest(replirev,leader, leaderip, myhost, myhostip) 
  insync(leaderip, leader) 
    
 return     

     
def _alive(val):
    return str(val) not in ('_1', '-1', '', 'None')

def tombstonesonreturn(leaderip, myhostip):
    # QSD5.346: a tombstone destroyedpool/<pool> written while this node was stopped never reached it: the sync request
    # is pruned as soon as every ACTIVE node acknowledged it (the stopped node is not counted), and a returning known node
    # runs restetcd (whole-etcd kinds only) + syncrequest, never the full copy of the etcdonly kinds (QSD5.345 proof: missing
    # 15 min after the return, isinsync yes).  When such a node took the leadership later, its import loop had no tombstone
    # and could take a stale copy of the deleted pool again.  So on return: (1) every tombstone of the leader is copied here;
    # (2) a tombstone only this node has is dropped when the pool is alive on the leader again (pools/<pool> or
    # ActPool/<pool>: imported on purpose with 'DGsetPool import', which deleted it on the leader while this node was away);
    # (3) otherwise it is kept (this node's import loop keeps skipping that name).  Runs before the whole-etcd copies,
    # because synckeys() ends the process (exit()) on a failed read.
    try:
        leaderstones = [x for x in get(leaderip, 'destroyedpool/', '--prefix')
                        if isinstance(x, tuple) and str(x[0]).startswith('destroyedpool/')]
        localstones = [x for x in get(myhostip, 'destroyedpool/', '--prefix')
                       if isinstance(x, tuple) and str(x[0]).startswith('destroyedpool/')]
    except Exception as e:
        print('tombstonesonreturn: no read', e)
        return
    local = dict(localstones)
    for key, val in leaderstones:
        if local.get(key) != val:
            put(myhostip, key, val)
            print('tombstone copied', key)
    leaderkeys = set(k for k, v in leaderstones)
    for key in local:
        if key in leaderkeys:
            continue
        pool = key.split('/', 1)[1]
        if pool and any(_alive(get(leaderip, pfx + pool)[0]) for pfx in ('pools/', 'ActPool/')):
            # exact key: etcddel.py with one argument also deletes keys named like the VALUE
            subprocess.run(['etcdctl', '--endpoints=http://' + myhostip + ':2379', 'del', key],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, ETCDCTL_API='3'))
            print('tombstone dropped, pool alive on the leader', key)
        else:
            print('tombstone kept (only here)', key)

def restetcd(leader,leaderip, myhost,myhostip):
    print('restetcd is',leader,leaderip,myhost,myhostip)
    if myhost == leader:
        return
    tombstonesonreturn(leaderip, myhostip)
    for sync in wholeetcd :
        if sync == 'Partnr':
            synckeys(leaderip, myhostip, 'Partner', 'Partner')
        else:
            synckeys(leaderip,myhostip, sync,sync)
 
runcmd={'Snapperiod':'etctocron'} 
synctypes={'syncinit':syncinit, 'syncrequest':syncrequest, 'syncall':syncall , 'restetcd': restetcd}


if __name__=='__main__':
    leaderip=sys.argv[2]
    myhost=sys.argv[3]
    leader = get(leaderip,'leader')[0]
    myhostip = get(leaderip,'ActivePartners/'+myhost)[0]
    if myhost == leader:
        myhostip = leaderip
 
    grpfninit(leader,leaderip, myhost,myhostip)
    usrfninit(leader,leaderip, myhost,myhostip)
    synctypes[sys.argv[1]](leader,leaderip, myhost,myhostip)

