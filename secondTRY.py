#!/bin/python3.6
import re
with open('zfslist.txt') as f:
     read_data = f.read()
     y = read_data.split("\n")

raidtypes=["'Common','Engineering','cifs1','repo'"]
zpool=[]

for a in y:
     b=a.split()
     c=re.split('; |, | |@',a)
     if "pdhc" in a:
          raidlist=[]
          zdict={}
          zdict={ 'name':c[0],"snapshot":c[1]}
          zpool.append(zdict)
          sdict={}
          zdict={ "CREATION":b[1:6]}
          zpool.append(zdict)

     elif any(raid in a for raid in raidtypes):

          rdict={ 'name':c[2],"snapshot":c[1]}
          raidlist.append(rdict)

     elif any(raid in a for raid in raidtypes):

          zdict={'name':c[0],"snapshot":c[1]}
          raidlist.append(rdict)


print(zpool)
