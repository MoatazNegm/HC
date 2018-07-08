#!/bin/python3.6
import re
with open('zfslist.txt') as f:
     read_data = f.read()
     y = read_data.split("\n")

zpool=[]

for a in y:
     b=a.split()
     c=re.split('; |, | |/|@',a)
     if "pdhc" in a and "/" not in a:
          volumes=[]
          zdict={}
          zdict={ 'PoolName':c[0] , "Volumes":volumes}
          zpool.append(zdict)
     if "pdhc" in a and "/" in a and "@" not in a:
         snapshots=[]
         rdict={}
         rdict={"Volname": c[1], "Snapshots":snapshots,"USED":b[6], "QUOTA":b[7], "USEDSNAP":b[8], "REFRATIO":b[9] ,"PROT:KIND":b[10]}
         volumes.append(rdict)
     if "pdhc" in a and "/" in a and "@" in a:
         rdict={}
         rdict={"snapname": c[2]}
         snapshots.append(rdict)

print(zpool)
