#!/usr/bin/python3
import subprocess,sys
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdput import etcdput as put
from etcddel import etcddel as dels 
from ast import literal_eval as mtuple
from socket import gethostname as hostname
from time import sleep

allusers= []
leader, leaderip, myhost, myhostip = '','','',''


def grpfninit(ldr,ldrip,hst,hstip,pprt='-1'):
 global allusers, leader ,leaderip, myhost, myhostip,pport
 leader, leaderip, myhost, myhostip, pport = ldr, ldrip, hst, hstip, pprt
 return
#def thread_add(*user):

def thread_add(user,syncip,pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip
 # QSD5.345: a group that is gone on the leader (an add request older than its delete request) reads back as the '_1'
 # placeholder string, not a (key, value) pair: user[1].split('/')[2] raised IndexError and the exception aborted the whole
 # sync pass on every round, so the follower acknowledged nothing any more and the cluster stayed out of sync (test 708/709).
 # Nothing to add then: the later delete request of the same group is applied as usual.
 if not isinstance(user, (list, tuple)) or len(user) < 2 or len(str(user[1]).split('/')) < 3:
  print('group add skipped, group not on the leader any more:', user)
  return
 username=user[0].replace('usersigroup/','')
 if 'Everyone' == username:
  return
 groupusers=user[1].split('/')[2]
 if groupusers=='no':
  groupusers='users'
 else:
  groupusers='users'+groupusers
 try:
  userigroup=user[1].split(':')
  userid=userigroup[0]
  usergd=userigroup[1]
 except:
    return
 cmdline=['/TopStor/UnixAddGroup',leaderip, username, groupusers, pullsync, userid,usergd, 'system']
 put(syncip, user[0],user[1])
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)

def groupnames(entries):
 # QSD5.345: the exact group names of a 'usersigroup --prefix' read ((key, value) pairs; '_1' / strings are no groups)
 names = set()
 for entry in entries if isinstance(entries, (list, tuple)) else []:
  if isinstance(entry, (list, tuple)) and len(entry) > 1 and str(entry[0]).startswith('usersigroup/'):
   names.add(str(entry[0]).split('/',1)[1])
 return names

#def thread_del(*user):
def thread_del(username,pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip
 if 'Everyone' == username:
  return
 print(username)
 # QSD5.345: exact name, not 'username not in str(allusers)': that text test found a short group name (ab, no, one) in any
 # other key or value (a member list, 'nogrouphome', 'Everyone') and kept a group the leader had deleted
 if username not in groupnames(allusers):
  print(username,str(allusers))
  cmdline=['/TopStor/UnixDelGroup',leaderip, username,'system',pullsync]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)

def groupsyncall(tosync=''):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 global myusers
 if 'pullsync' in tosync:
    allusers=getnoport(leaderip,pport,'usersigroup','--prefix')
 else:
    allusers=get(leaderip,'usersigroup','--prefix')
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 myusers=get(syncip,'usersigroup','--prefix')
 print(';;;;;',myusers,allusers)
 threads=[]
 if '_1' in allusers:
  allusers=[]
 if '_1' in myusers:
  myusers=[]
 # QSD5.345: a local group is stale when its NAME is gone on the leader (OS group and local key deleted together); a group
 # that is still there with other members is rewritten by the add loop below (comparing whole (key, value) pairs deleted
 # the local key of every changed group and then kept its OS group through the text test)
 leadernames = groupnames(allusers)
 for user in myusers:
  if not isinstance(user, (list, tuple)) or len(user) < 2:
   continue
  if str(user[0]).split('/',1)[-1] not in leadernames:
   groupkey = user[0]
   thread_del(groupkey.split('/')[1])
   dels(syncip, groupkey)      # QSD5.345: was dels(syncip, <first letter of the name>), the stale key stayed

 for user in allusers:
  print(user)
  thread_add(user,syncip)
  put(syncip, user[0],user[1])
   
def addmissinggroups():
 # QSD5.352 fix17 (QC 628): a member that missed a group add (request marked done, or lost while the node was down) never got
 # it back: a node the cluster knows runs only 'syncrequest' at boot, and only 'syncall' compares the group lists.  Here the
 # member compares the group NAMES with the leader's on every syncrequest pass and adds the missing ones the normal way
 # (onegroupsync -> thread_add -> UnixAddGroup pull).  Only adds; deletes stay with their own requests.
 global leader, leaderip, myhost, myhostip
 if not myhost or myhost in leader:
  return
 leadergroups = get(leaderip,'usersigroup','--prefix')
 if '_1' in leadergroups:
  return                  # failed read of the leader: try again next pass, never act on it
 localgroups = get(myhostip,'usersigroup','--prefix')
 if '_1' in localgroups:
  localgroups = []
 localnames = groupnames(localgroups)
 for name in sorted(groupnames(leadergroups) - localnames):
  if name == 'Everyone':
   continue
  print('group missing on this member, adding it:', name)
  onegroupsync('Add', name, 'pullavail')

def onegroupsync(oper,usertosync,tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 if oper == 'Add':
    # QSD5.345: the exact key of this group (the search by text also returned other groups whose value merely contains
    # the name, and [0] could be one of them)
    # QSD5.352 fix17 (QC 628, QX-029 step 4): etcdget answers '_1' for ANY failed read (a busy leader, the 2 s limit), the
    # same as for a missing key; one failed read was taken as 'group gone', the request was marked done anyway and the member
    # never got the group (qg1 created 2 s before qg2).  Read again before giving up (up to 5 times, 2 s apart).
    for _try in range(5):
        if 'pullsync' in tosync:
            found=getnoport(leaderip, pport, 'usersigroup/'+usertosync)
        else:
            found=get(leaderip,'usersigroup/'+usertosync)
        value=str(found[0]) if len(found) > 0 else '_1'
        if value not in ('_1', '-1', '', 'None'):
            break
        sleep(2)
    if value in ('_1', '-1', '', 'None'):
        print('group add skipped, group not on the leader any more:', usertosync)
        return
    thread_add(('usersigroup/'+usertosync, value),syncip)
 else:
    user = usertosync
    thread_del(user,tosync)
    
 
  
if __name__=='__main__':
 with open('/root/sync2','w') as f:
  f.write('Starting\n')

 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
 leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
 leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
 myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
 myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 if len(sys.argv[1:]) < 2:
    print(' syncing all groups')
    groupsyncall(*sys.argv[1:])
 else:
    onegroupsync(*sys.argv[1:])
