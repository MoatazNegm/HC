#!/bin/python3.6
import subprocess
from ast import literal_eval as mtuple
import socket

myhost=socket.gethostname()
#cmdline=['/pace/etcdget.py','known','--prefix']
#result=subprocess.run(cmdline,stdout=subprocess.PIPE)
#known=str(result.stdout).replace('known/','')[2:][:-3].split('\\n')
#if known==['']:
# print('no partners')
# exit();
cmdline=['/pace/etcdget.py','broadcast/confirmed','--prefix']
result=subprocess.run(cmdline,stdout=subprocess.PIPE)
conf=str(result.stdout).replace('broadcast/confirmed/','')[2:][:-3].split('\\n')
if conf != ['']:
 cmdline=['/pace/etcddel.py','broadcast','--prefix']
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 exit()
cmdline=['/pace/etcdget.py','broadcast/response/'+myhost,'--prefix']
result=subprocess.run(cmdline,stdout=subprocess.PIPE)
respo=str(result.stdout).replace('broadcast/response/'+myhost,'')[2:][:-3].split('\\n')
if respo != ['']:
 exit()
  
cmdline=['/pace/etcdget.py','broadcast/request','--prefix']
result=subprocess.run(cmdline,stdout=subprocess.PIPE)
br=str(result.stdout).replace('broadcast/request/','')[2:][:-3].split('\\n')
if br==['']:
 print('no request')
 exit();
broad=[]
for c in br:
 if myhost in mtuple(c)[0]:
  continue
 broad.append(mtuple(c))
print(broad)
if broad == []:
  exit()
start=min(broad,key=lambda t: t[1])
broad=[]
counter=0
with open('/var/www/html/des20/Data/TopStor.log','rt') as f:
 revf=f.readlines()[::-1]
 for line in revf:
  line=str(line).split(' ')
  try:
   if int(start[1]) <= int(line[5]):
    counter+=1
    line[5]=line[5].replace('\n','')
    broad.append(line)
  except:
   pass  
 if counter > 0:
  cmdline=['/pace/etcdput.py','broadcast/response/'+myhost,str(broad)]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)
