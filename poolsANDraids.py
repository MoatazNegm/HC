#!/bin/python3.6
with open('zpool.txt') as f:
     read_data = f.read()
     y = read_data.split("\n")
raidtypes=['mirror','raidz','stripe']
raid2=['log','cache','spare']
zpool=[]
for a in y:
 b=a.split()
 if "pdhc" in a and  'pool' not in a:
  raidlist=[]
  zdict={}
  zdict={ 'name':b[0], 'status':b[1], 'raidlist': raidlist }
  zpool.append(zdict)
 elif any(raid in a for raid in raidtypes):
  disklist=[]
  rdict={ 'name':b[0], 'status':b[1],'disklist':disklist }
  raidlist.append(rdict)
 elif any(raid in a for raid in raidtypes):
  disklist=[]
  zdict={ 'name':b[0], 'status':'NA','disklist':disklist }
  raidlist.append(rdict)
 elif 'scsi' in a:
   zdict={'name':b[0], 'status':b[1]}
   disklist.append(zdict)
 else:
   zdict={'name':'na','status':a}
   #zpool.append(zdict)
   
print(zpool)
