#!/usr/bin/python3
# activeusers.py <leaderip> <myhost> -- the clients connected to the volumes of THIS node (QSD5.344, test 658 QX-059 step 3).
# Run by zfsping.py (activeusersproc, about every 30 s) on every node.  One etcd key per node on the leader's etcd:
#   connections/<myhost> = {"stamp": <epoch>, "node": <myhost>, "connections": [ {volume, fullname, protocol, user, client, node}, ... ]}
# The key is rewritten every cycle with the full set of this node, so a closed client is gone after one cycle; the API
# (fapi getconns) skips a node whose stamp is older than 90 s (a dead node, a stopped collector).
#   CIFS/HOME  docker exec <CIFS|HOME...>-<ip> smbstatus -b (pid, user, machine) and -S (share, pid): the share is the volume
#   NFS        docker exec NFS-<ip>: /proc/fs/nfsd/clients/*/info (NFSv4 clients of the nfsd of the container); every NFS
#              volume of that address of this node
#   ISCSI      LIO configfs /sys/kernel/config/target/iscsi/<target>/tpgt_*/acls/<initiator>/info (Address of the session);
#              only targets with a LUN on an ISCSI volume of this node (the nodes of the container flavour share one LIO)
# (The old version matched lowercase "cifs-" containers -- they are CIFS-<ip> --, used the etcdput/etcddel signatures without
# the etcd address, stored the share address as the volume and never removed the keys of a stopped share or node.)
import sys, os, re, json, subprocess
from time import time as stamp
from etcdgetpy import etcdget as get
from etcdput import etcdput as put

LIO = '/sys/kernel/config/target/iscsi'

def run(cmd, timeout=15):
 try:
  return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout).stdout.decode('utf-8', 'replace')
 except Exception as e:
  print('activeusers: '+' '.join(cmd)+': '+str(e))
  return ''

def readfile(path):
 try:
  with open(path, 'r', errors='replace') as f:
   return f.read()
 except Exception:
  return ''

def short(fullname):
 return fullname.split('_')[0]

def myvolumes(leaderip, myhost):
 # {prot: {fullname: ip}} of the volumes of this node (etcd volumes/<prot>/<host>/<pool>/<name>, fields as allphysicalinfo.py)
 vols = {'CIFS': {}, 'HOME': {}, 'NFS': {}, 'ISCSI': {}}
 ipfield = {'CIFS': 7, 'HOME': 7, 'NFS': 9, 'ISCSI': 2}
 for vol in get(leaderip, 'volumes', '--prefix'):
  try:
   key = vol[0].split('/')
   val = vol[1].split('/')
   prot = key[1]
   if prot not in vols or key[2] != myhost:
    continue
   vols[prot][val[1]] = val[ipfield[prot]]
  except Exception:
   continue
 return vols

def entry(fullname, prot, user, client, myhost):
 return {'volume': short(fullname), 'fullname': fullname, 'protocol': prot, 'user': user, 'client': client, 'node': myhost}

def cifsconns(names, vols, myhost):
 conns = []
 smbvols = dict(vols['CIFS'])
 smbvols.update(vols['HOME'])
 for name in names:
  if '-' not in name or not (name.startswith('CIFS') or name.startswith('HOME')):
   continue
  ip = name.split('-')[-1]
  users = {}
  for line in run(['docker', 'exec', name, 'smbstatus', '-b']).split('\n'):
   f = line.split()
   if len(f) >= 4 and f[0].isdigit():
    users[f[0]] = (f[1], f[3])			# pid: user, machine
  if len(users) == 0:
   continue
  for line in run(['docker', 'exec', name, 'smbstatus', '-S']).split('\n'):
   f = line.split()
   if len(f) < 3 or not f[1].isdigit() or f[1] not in users or f[0] == 'IPC$':
    continue
   service = f[0]
   if service not in smbvols:
    ipvols = [v for v in smbvols if smbvols[v] == ip]
    if len(ipvols) == 1:
     service = ipvols[0]				# a share named otherwise (home share) on a one-volume address
   prot = 'HOME' if service in vols['HOME'] or name.startswith('HOME') else 'CIFS'
   conns.append(entry(service, prot, users[f[1]][0], users[f[1]][1], myhost))
 return conns

def nfsconns(names, vols, myhost):
 conns = []
 for name in names:
  if not name.startswith('NFS-'):
   continue
  ip = name.split('-')[-1]
  ipvols = [v for v in vols['NFS'] if vols['NFS'][v] == ip]
  if len(ipvols) == 0:
   continue
  out = run(['docker', 'exec', name, 'sh', '-c', 'for f in /proc/fs/nfsd/clients/*/info; do [ -f "$f" ] && echo "==client==" && cat "$f"; done'])
  clients = []
  for block in out.split('==client==')[1:]:
   addr = re.search(r'address:\s*"?([^"\s]+)"?', block)
   status = re.search(r'status:\s*(\S+)', block)
   if addr is None or (status is not None and status.group(1) not in ('confirmed', 'unconfirmed')):
    continue						# courtesy/expirable: the client is gone, nfsd only keeps its state
   client = addr.group(1)
   if client.startswith('['):
    client = client[1:].split(']')[0]			# [ipv6]:port
   elif client.count(':') == 1:
    client = client.split(':')[0]			# ipv4:port
   if client not in clients:
    clients.append(client)
  for client in clients:
   for vol in ipvols:
    conns.append(entry(vol, 'NFS', '-', client, myhost))
 return conns

def iscsiconns(vols, myhost):
 conns = []
 if not os.path.isdir(LIO) or len(vols['ISCSI']) == 0:
  return conns
 for target in os.listdir(LIO):
  tdir = LIO+'/'+target
  if not target.startswith(('iqn.', 'naa.', 'eui.')):
   continue
  for tpg in [x for x in os.listdir(tdir) if x.startswith('tpgt_')]:
   tpgdir = tdir+'/'+tpg
   tvols = []
   try:
    for lun in os.listdir(tpgdir+'/lun'):
     for link in os.listdir(tpgdir+'/lun/'+lun):
      if os.path.islink(tpgdir+'/lun/'+lun+'/'+link):
       so = os.path.basename(os.path.realpath(tpgdir+'/lun/'+lun+'/'+link))	# the backstore: <dev>-<host>-<volume>
       tvols += [v for v in vols['ISCSI'] if v in so and v not in tvols]
   except Exception:
    pass
   if len(tvols) == 0:
    continue						# no LUN of a volume of this node (disk targets, other nodes)
   try:
    acls = os.listdir(tpgdir+'/acls')
   except Exception:
    acls = []
   for acl in acls:
    info = readfile(tpgdir+'/acls/'+acl+'/info')
    if 'InitiatorName' not in info:
     continue						# "No active iSCSI Session for Initiator Endpoint"
    addrs = re.findall(r'Address\s+(\S+)\s+(?:TCP|SCTP|iSER)', info)
    for vol in tvols:
     conns.append(entry(vol, 'ISCSI', acl, addrs[0] if addrs else acl, myhost))
   for acl in readfile(tpgdir+'/dynamic_sessions').split():	# sessions without an ACL (generate_node_acls)
    if acl.startswith(('iqn.', 'naa.', 'eui.')):
     for vol in tvols:
      conns.append(entry(vol, 'ISCSI', acl, acl, myhost))
 return conns

def activeusers(leaderip, myhost):
 vols = myvolumes(leaderip, myhost)
 names = run(['docker', 'ps', '--format', '{{.Names}}']).split()
 conns = []
 for collect in (lambda: cifsconns(names, vols, myhost), lambda: nfsconns(names, vols, myhost), lambda: iscsiconns(vols, myhost)):
  try:
   conns += collect()
  except Exception as e:
   print('activeusers: '+str(e))
 put(leaderip, 'connections/'+myhost, json.dumps({'stamp': int(stamp()), 'node': myhost, 'connections': conns}, separators=(',', ':')))
 return conns

if __name__=='__main__':
 leaderip = sys.argv[1]
 myhost = sys.argv[2]
 print(json.dumps(activeusers(leaderip, myhost)))
