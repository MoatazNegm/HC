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
          zdict={ 'name':c[0],"snapshot":c[1] ,"USED":b[6], "QUOTA":b[7], "USEDSNAP":b[8], "REFRATIO":b[9] ,"PROT:KIND":b[10]}
          zpool.append(zdict)


     elif any(raid in a for raid in raidtypes):

          rdict={ 'name':c[0],"snapshot":c[1]}
          raidlist.append(rdict)



print(zpool)
