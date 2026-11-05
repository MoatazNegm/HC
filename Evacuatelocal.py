#!/usr/bin/python3
import subprocess,sys, datetime
from etcddel import etcddel as deli 
from etcdput import etcdput as put 


# QSD5.352 r2 (validator R1): sync/evacuatehost/ stays too.  The request sync/evacuatehost/syncfn_setall_<host>_<user>/request
# names the host between '_' and matched the whole-word pattern, so the leader deleted the request itself: a follower that
# had not run it yet never ran removetargetdisks.sh / hostlost.sh for the removed node (stale iSCSI sessions and disks with
# 3+ nodes), and checksyncs wrote the leader's done mark .../request/<leader> again afterwards.  The leader's normal pruning
# removes the request once every active node has acknowledged it.
# QSD5.352 r9c (prover r4 D7): only the request and its acknowledgements (sync/evacuatehost/syncfn_..., both forms:
# TopStor/Evacuate.py syncfn_setall_<host>_<user>, pace/Evacuateleader.py syncfn_setall_<host>_<ip>_<user>).  The whole
# sync/evacuatehost/ prefix also kept the removed node's initial-sync mark sync/evacuatehost/initial/request/<host>; the
# leader's pruning skips every 'initial' key, so it stayed for good and survived the rejoin.
KEEP_PREFIXES = ('log/', 'sync/log/', 'notification', 'excepts/', 'sync/evacuatehost/syncfn_')

def delhostkeys(etcdip, hostn):
 # QSD5.352 (QC 687, 699): after an evacuation the leader kept alias/, cversion/, ipaddr/, configured/, excepts, ntp, ports,
 # nextlead/er and ~70 sync/* keys of the removed node (a second alias with the same name, the old address still taken).
 # The cleanup ran only against this node's own address and matched the host name as a SUBSTRING of key or value (dhcp2434
 # would also have hit dhcp243499).  Now: every key whose name or value holds the host name as a whole word, on the given
 # etcd, deleted by its exact key; the log rows (they name the node) and excepts/ stay.
 import re
 pat = re.compile(r'(^|[^A-Za-z0-9])'+re.escape(str(hostn))+r'([^A-Za-z0-9]|$)')
 if not hostn or not etcdip:
  return 0
 try:
  out = subprocess.run(['etcdctl','--endpoints=http://'+etcdip+':2379','get','','--prefix'],
                       stdout=subprocess.PIPE, timeout=10).stdout.decode('utf-8', 'replace')
 except Exception as e:
  print('evacuate cleanup: no etcd at', etcdip, e)
  return 0
 lines = out[:-1].split('\n') if out.endswith('\n') else out.split('\n')
 count = 0
 for key, value in zip(lines[0::2], lines[1::2]):
  if key.startswith(KEEP_PREFIXES):
   continue
  if pat.search(key) or pat.search(value):
   try:
    subprocess.run(['etcdctl','--endpoints=http://'+etcdip+':2379','del',key], stdout=subprocess.PIPE, timeout=10)
   except Exception as e:
    print('evacuate cleanup: delete of', key, 'failed', e)
    continue
   count += 1
 print('evacuate cleanup:', count, 'keys of', hostn, 'removed from', etcdip)
 return count

def setall(hostn,*arg):

 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
 myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 print('hihihih')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
 myip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py ActivePartners/'+hostn
 hostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
 leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
 leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 if myhost in hostn:
  put(leaderip, 'configured/'+hostn,'reset')
  put(myip, 'configured/'+hostn,'reset')
  put(leaderip, 'rebootme/'+hostn,'pls_fromevacuate')
  cmdline=['/TopStor/docker_setup.sh','reset']
  #result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 else:
    cmdline=['/pace/removetargetdisks.sh', hostn, hostip]
    result=subprocess.run(cmdline,stdout=subprocess.PIPE)
    cmdline=['/pace/hostlost.sh',leader, leaderip, myhost, myip, hostn]
    result=subprocess.run(cmdline,stdout=subprocess.PIPE)
    delhostkeys(myip, hostn)
    if leader == myhost and leaderip and leaderip != myip:
     delhostkeys(leaderip, hostn)      # the leader's cluster etcd is the one every node copies

if __name__=='__main__':
 setall(*sys.argv[1:])
