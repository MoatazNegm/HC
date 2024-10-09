#!/usr/bin/python3
import subprocess,sys
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdput import etcdput as put
from etcddel import etcddel as dels 
from ast import literal_eval as mtuple

leader, leaderip, myhost, myhostip = '','','',''
def usrfninit(ldr,ldrip,hst,hstip,pprt='-1'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 leader, leaderip, myhost, myhostip, pport = ldr, ldrip, hst, hstip, pprt
 return
allusers = []

def thread_add(user,syncip, tosync='pullavail'):
 global myusers
 global allusers, leader ,leaderip, myhost, myhostip,pport
 username=user[0].replace('usersinfo/','')
 if 'NoUser' == username:
  return
 with open('/root/usersync2','w') as f:
  f.write(str(user)+' + '+str(username)+'\n')
 
 if 'pullsync' in tosync:
    userhash=getnoport(leaderip,pport,'usershash/'+username)[0]
    everyone=getnoport(leaderip,pport,'usersigroup/Everyone',username)
    if '_1' not in str(everyone):
        everyone=',Everyone'
    else:
        everyone=''
 else:
    userhash=get(leaderip,'usershash/'+username)[0]
    everyone=get(leaderip, 'usersigroup/Everyone',username)
    if '_1' not in str(everyone):
        everyone=',Everyone'
    else:
        everyone=''
 userinfo=user[1].split(':')
 userid=userinfo[0]
 usergd=userinfo[1]
 usersplit = user[1].split('/')
 homePool = usersplit[1]
 usergroups = usersplit[2] 
 userpass = userhash
 size = usersplit[3]
 HomeAddr = usersplit[-3]
 HomeSubnet = usersplit[-2]
 active = usersplit[-1]
 permissions = ",".join(usersplit[4:-3])
 cmdline=['/TopStor/UnixAddUser',leaderip,username, homePool, 'groups'+usergroups+everyone,userhash, size, HomeAddr, HomeSubnet, tosync, userid,usergd,active, permissions,'system']
 print('***************************')
 print(cmdline)
 print('***************************')
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)

def thread_del(username,syncip, pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip
 global allusers
 if  'NoUser' == username:
  return
 if username not in str(allusers) and 'admin' != username:
  cmdline=['/TopStor/UnixDelUser',leaderip, username,'system',pullsync]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)
  dels(syncip,'user',username)

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
 leader=get(leaderip,'leader','--prefix')
 if myhost not in str(leader) or 'pullsync' in tosync:
  for user in myusers:
   if user not in allusers:
     user=user[0].replace('usersinfo/','')
     thread_del(user, syncip, tosync)

def oneusersync(oper,usertosync,tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 print('args',oper,usertosync)
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 
 if oper == 'Add':
    if 'pullsync' in tosync:
        user=getnoport(leaderip,pport,'usersinfo', usertosync)[0]
    else:
        user=get(leaderip,'usersinfo', usertosync)[0]
    thread_add(user,syncip,tosync)
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
