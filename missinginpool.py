#!/usr/bin/python3
import subprocess,sys
from etcdgetpy import etcdget as get
from ast import literal_eval as mtuple

cmdline=['/sbin/zpool', 'status']
result=subprocess.run(cmdline,stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
mylist=str(result.stdout)[2:][:-3].split('\\n')
mylist=[x.split()[1] for x in mylist if 'ONLINE' in x and 'scsi' in x]
cmdline=['/bin/lsscsi', '-i']
result=subprocess.run(cmdline,stdout=subprocess.PIPE)
l2=str(result.stdout)[2:][:-3].split('\\n')
l2=['scsi-'+x.split()[6] for x in l2 if 'LIO' in x] 
z=set(mylist).difference(l2)
pool=get('run','--prefix')
pool=[x for x in pool if ('name' in str(x) and 'pool' in str(x)) ]
pool=mtuple(str(pool)[1:][:-1])
pool=pool[1]
for x in z:
 cmdline=['/sbin/zpool','offline',pool,x]
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
