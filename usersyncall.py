#!/usr/bin/python3
import subprocess,sys
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdput import etcdput as put
from etcddel import etcddel as dels 
from ast import literal_eval as mtuple
from time import time as _timestamp

leader, leaderip, myhost, myhostip = '','','',''
def usrfninit(ldr,ldrip,hst,hstip,pprt='-1'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 leader, leaderip, myhost, myhostip, pport = ldr, ldrip, hst, hstip, pprt
 return
allusers = []

def localgroup(name):
 # the group exists on this node (getent group)
 try:
  return subprocess.run(['getent','group',name],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).returncode == 0
 except Exception:
  return False

# QSD5.352 r9c (prover r4 D8): a usersinfo value that is no user record.  A HOME create for a name without a record
# (volumes/create type=HOME, before r9) stored usersinfo/<home name> = '_1///<size>': 4 '/' fields, so it passed the
# check below, and 'usergd=userinfo[1]' raised IndexError.  The whole sync pass died there on every loop: a joining
# node never finished its initial sync (isinsync no), the users that sort after the record were never created and users
# deleted on the leader were never removed (the delete loop runs after the add loop).  A user record is
# '<uid>:<gid>:/<pool>/<name>/<size>[/...]' (UnixAddUser; Priv.py and VolumeQuotaHOME keep the first four fields).
# Anything else is skipped and logged once (per name and value) in SKIPLOG; it is not deleted here (the leader's
# VolumeDeleteHOME removes it with the home, an existing one is removed by hand).
SKIPLOG = '/root/usersyncskip.log'
_skipped = set()
def userrecord(value):
 import re
 fields = str(value).split('/')
 return len(fields) >= 4 and re.match(r'^[0-9]+:[0-9]+:$', fields[0]) is not None

def skiprecord(key, value):
 line = str(key)+' = '+repr(str(value))
 if line in _skipped:
  return
 _skipped.add(line)
 try:
  try:
   with open(SKIPLOG) as f:
    if any(l.rstrip('\n').endswith(' '+line+' skipped: no user record (<uid>:<gid>:/<pool>/<name>/<size>)') for l in f):
     return
  except FileNotFoundError:
   pass
  from datetime import datetime
  with open(SKIPLOG, 'a') as f:
   f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' '+line+' skipped: no user record (<uid>:<gid>:/<pool>/<name>/<size>)\n')
  print('user add skipped, no user record:', line)
 except Exception as e:
  print('user add skipped, no user record:', line, e)

def thread_add(user,syncip, tosync='pullavail'):
 global myusers
 global allusers, leader ,leaderip, myhost, myhostip,pport
 # QSD5.345: a user that is gone on the leader reads back as the '_1' placeholder string, not a (key, value) pair; the
 # index errors below then aborted the whole sync pass (same as the group add, groupsyncall.thread_add)
 # QSD5.352 (QC 685): users/usersauth (Priv.py) keeps the first four fields (uid:gid:, pool, name, size) and appends the
 # privileges it was given, so a record like 1004:1004:/NoHome/qu2/1G/Logs-true has 5 fields.  The old limit of 6 skipped
 # such a user for good: no follower (or joining node) ever created it.  4 fields are enough for the copy.
 if not isinstance(user, (list, tuple)) or len(user) < 2 or len(str(user[1]).split('/')) < 4:
  print('user add skipped, user not on the leader any more:', user)
  return
 username=str(user[0]).replace('usersinfo/','')
 if 'NoUser' == username:
  return
 if not userrecord(user[1]):
  skiprecord(user[0], user[1])
  return
 with open('/root/usersync2','w') as f:
  f.write(str(user)+' + '+str(username)+'\n')
 
 if 'pullsync' in tosync:
    userhash=getnoport(leaderip,pport,'usershash/'+username)[0]
    allgroups=getnoport(leaderip,pport,'usersigroup','--prefix')
 else:
    userhash=get(leaderip,'usershash/'+username)[0]
    allgroups=get(leaderip,'usersigroup','--prefix')
 # QSD5.345: the groups of the user are the groups whose member list (third field of usersigroup/<group>) names this user
 # exactly.  The copy used to pass usersplit[2] of usersinfo/<user> -- which is the user NAME, not a group list -- so the
 # follower's UnixAddUser (userdel -f + useradd) and the UnixChangeUser after it left the user in no group but Everyone and
 # took the user out of every group in the follower's own etcd: usersigroup/<group> NoUser and an empty /etc/group line on
 # the follower while the leader listed the member (QC tests 638, 678; usr1/grp1 in test 14).  Only groups that exist on
 # this node are given (usermod -G fails as a whole on one unknown group); a group that arrives later adds its members
 # itself (UnixAddGroup -> UnixChangeGroup).
 mygroups = []
 for grp in allgroups:
  if not isinstance(grp, (list, tuple)) or len(grp) < 2:
   continue
  gname = str(grp[0]).replace('usersigroup/','')
  fields = str(grp[1]).split('/')
  if len(fields) < 3 or gname in mygroups:
   continue
  if username in fields[2].split(',') and localgroup(gname):
   mygroups.append(gname)
 if 'Everyone' not in mygroups and localgroup('Everyone'):
  mygroups.append('Everyone')
 groupsarg = 'groups'+(','.join(mygroups) if mygroups else 'NoGroup')
 userinfo=user[1].split(':')
 userid=userinfo[0]
 usergd=userinfo[1]
 usersplit = user[1].split('/')
 homePool = usersplit[1]
 userpass = userhash
 size = usersplit[3]
 if len(usersplit) >= 8:
  HomeAddr = usersplit[-3]
  HomeSubnet = usersplit[-2]
  active = usersplit[-1]
  permissions = ",".join(usersplit[4:-3])
 else:
  # short record (see above): no address fields; a copy (pullsync) does not create the home anyway
  HomeAddr, HomeSubnet, active = 'no', 'no', 'no'
  permissions = ",".join(usersplit[4:])
 if not permissions:
  permissions = 'no'      # an empty argument vanishes in UnixAddUser's 'echo $@ | awk' and shifts the request user
 cmdline=['/TopStor/UnixAddUser',leaderip,username, homePool, groupsarg,userhash, size, HomeAddr, HomeSubnet, tosync, userid,usergd,active, permissions,'system']
 print('***************************')
 print(cmdline)
 print('***************************')
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)

def thread_del(username,syncip, pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip
 global allusers
 if  'NoUser' == username:
  return
 # QSD5.350: the exact key usersinfo/<name> ('username not in str(allusers)' was a substring test over keys AND values:
 # a user 'q1' that was deleted while this node was down stayed here as long as the leader had q1-admin, q10, ... or a
 # value with 'q1' in it)
 leadernames = set(str(x[0]) for x in allusers if isinstance(x, (list, tuple)) and len(x) == 2)
 if 'usersinfo/'+username not in leadernames and 'admin' != username:
  cmdline=['/TopStor/UnixDelUser',leaderip, username,'system',pullsync]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)
  # exact keys only: dels(syncip,'user',username) removed every key whose text merely contained the name
  # (deleting usr1 also deleted usr10..usr16)
  dels(syncip,'usersinfo/'+username)
  dels(syncip,'usershash/'+username)

def followadminhash(leaderip, myhostip):
 """admin has no usersinfo, so no UnixAddUser carries its hash to a follower: a follower that never ran a full user
 sync (QSD5.328: only user adds happened since it joined) had no usershash/admin, and after a fail over the new leader
 answered baduser for admin.  A node that was down while the admin password changed kept the old one and handed it to
 the cluster when it became the leader.  Copy the leader's hash into this node's own etcd when it differs."""
 try:
  newhash = str(get(leaderip,'usershash/admin')[0]).replace('\n','')
  if newhash not in ('_1','-1','','None') and len(newhash) > 3 and newhash != str(get(myhostip,'usershash/admin')[0]).replace('\n',''):
   put(myhostip,'usershash/admin',newhash)
   subprocess.run(['/TopStor/UnixChangePass','admin','admin'],stdout=subprocess.PIPE)
 except Exception as e:
  print('admin hash sync', e)

def usersyncall(tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip,pport
 global allusers
 global myusers
 if 'pullsync' in tosync:
    allusers=getnoport(leaderip,pport,'usersinfo','--prefix')
 else:
    allusers=get(leaderip,'usersinfo','--prefix')
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 myusers=get(syncip,'usersinfo','--prefix')
 threads=[]
 if '_1' in allusers:
  allusers=[]
 if '_1' in myusers:
  myusers=[]
 for user in allusers:
  thread_add(user,syncip, tosync)
 if 'pullsync' in tosync:
  pulladminhash('admin')
 elif myhost not in str(leader):
  # admin has no usersinfo, so no UnixAddUser above carries its hash: see followadminhash
  followadminhash(leaderip, myhostip)
 leader=get(leaderip,'leader','--prefix')
 if myhost not in str(leader) or 'pullsync' in tosync:
  for user in myusers:
   # r9c (D8): one bad entry must not stop the pass (a '_1' placeholder or a pair without a key)
   if not isinstance(user, (list, tuple)) or len(user) < 2:
     continue
   if user not in allusers:
     user=str(user[0]).replace('usersinfo/','')
     thread_del(user, syncip, tosync)

def pulladminhash(username='admin'):
 """Receiver (DR site) side of the replication: the password hash of `username` on the sending cluster replaces the one
 on this cluster, so the sender's admin password also logs in here (QualityCheck replication tests).  The hash is
 encrypted with a key that depends only on the user name, so it is valid on any cluster.  The new hash is stored in
 this cluster's leader etcd and a 'passwd' sync request makes every node apply it (UnixChangePass reads it from etcd).
 Only for admin and for users that already exist here (their own usersinfo), never creates a stray usershash key."""
 global leaderip, pport
 try:
  newhash = str(getnoport(leaderip, pport, 'usershash/'+username)[0]).replace('\n','')
  oldhash = str(get(leaderip, 'usershash/'+username)[0]).replace('\n','')
  if username != 'admin' and str(get(leaderip, 'usersinfo/'+username)[0]) in ('_1', '-1', '', 'None'):
   return False
 except Exception as e:
  print('pulladminhash: cannot read the hash of', username, e)
  return False
 if len(newhash) < 3 or newhash == '_1' or newhash == oldhash:
  return False
 print('pulladminhash: the password of', username, 'follows the sending cluster')
 put(leaderip, 'usershash/'+username, newhash)
 dels(leaderip, 'sync', 'UnixChangePass_'+username+'_')
 put(leaderip, 'sync/passwd/UnixChangePass_'+username+'_admin/request', 'passwd_'+str(int(_timestamp()*1000)))
 return True

def oneusersync(oper,usertosync,tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 print('args',oper,usertosync)
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 
 if oper == 'Add':
    # QSD5.345: the exact key of this user (the search by text returned the first user whose key or value merely
    # CONTAINS the name: usr1 -> usr10 when usr1 is gone)
    if 'pullsync' in tosync:
        found=getnoport(leaderip,pport,'usersinfo/'+usertosync)
    else:
        found=get(leaderip,'usersinfo/'+usertosync)
    value=str(found[0]) if len(found) > 0 else '_1'
    if value in ('_1', '-1', '', 'None'):
        print('user add skipped, user not on the leader any more:', usertosync)
        return
    thread_add(('usersinfo/'+usertosync, value),syncip,tosync)
 else:
    user = usertosync
    thread_del(user,syncip,tosync)
 
  
if __name__=='__main__':
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
 leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
 leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
 myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
 myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 if len(sys.argv[1:]) < 2:
    usersyncall(*sys.argv[1:])
 else:
    oneusersync(*sys.argv[1:])
