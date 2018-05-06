#!/bin/python3.6
import nmap
import sys, subprocess

ip=sys.argv[1].split('.')
hostrange=ip[0]+'.'+ip[1]+'.'+ip[2]+'.0'
nm=nmap.PortScanner()
nm.scan(hostrange+'/24','5672')
serverstatus='nothing'
#subprocess.run('export','ETCDCTL_API=3')
hostlist=[nm[x] for x in nm.all_hosts() if 'up' in nm[x]['status']['state']]
for host in hostlist:
 cmdline=['etcdctl','-w','json','--endpoints='+host['addresses']['ipv4']+':2379','member','list','2>/dev/null']
#subprocess.run('export','ETCDCTL_API=3')
for host in nm.all_hosts():
 cmdline=['etcdctl','-w','json','--endpoints='+host+':2379','member','list']
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 if result.returncode==0:
  etcdserver=host
  serverstatus=result.stdout
serverstatus=str(serverstatus)[2:]
serverstatus=serverstatus[:-3]
if len(serverstatus) < 6:
 serverstatus='nothing'
etcdfile=open('/pacedata/runningetcdnodes.txt','w')
etcdfile.write(serverstatus)
etcdfile.close()
print(serverstatus)
