#!/usr/bin/python3
import subprocess,sys, datetime, time
from etcdgetpy import etcdget as get

# QSD5.349: the read of the table, the read of the Snapperiod records and the install run under the lock that
# TopStor/DGdestroyPool takes for its filter (flock on /TopStordata/cronfile.lock).  Without it an etctocron that read the
# table (or the records) before a pool delete and installed after the delete's filter wrote the deleted pool's lines back
# (a 'pump.sh RemoteSnapshotnowOnce' line of the pool: etctocron keeps every line without 'nowhost'), and two etctocron
# runs at once shared /TopStordata/crons.  Not taken in 60 s (or the lock file cannot be opened): it runs without it.
LOCKFILE = '/TopStordata/cronfile.lock'
LOCKWAIT = 60

def cronlock(path=LOCKFILE, wait=LOCKWAIT):
 try:
  import fcntl
  f = open(path, 'a')
 except Exception:
  return None
 end = time.time() + wait
 while True:
  try:
   fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
   return f
  except (BlockingIOError, PermissionError):
   if time.time() >= end:
    f.close()
    return None
   time.sleep(0.2)
  except Exception:
   f.close()
   return None

def etctocron(leaderip, period='--prefix'):
 lock = cronlock()
 try:
  _etctocron(leaderip, period)
 finally:
  if lock is not None:
   lock.close()

def _etctocron(leaderip, period='--prefix'):
 cmdline='/bin/crontab -l'
 crons=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout
 crons=str(crons).replace("b'","").split('\\n')
 crons=[x for x in crons if 'nowhost' not in x and len(x) > 5 ]
 cronstr=''
 for x in crons:
  cronstr+=x+'\n'
 etccron=get(leaderip,'Snapperiod',period)
 for x in etccron:
  cronid = str(x[0].split('/')[4])
  yleft=str(x[1].split('/TopStor')[0].replace('%',' '))
  yright=x[1].split('/TopStor')[1].replace('%',' ')
  cronstr += yleft+' /TopStor/putcron.sh /TopStor/etcdput.py '+leaderip+' call/'+cronid+' /TopStor'+yright.replace(' ','::')+'\n'
 print(cronstr)
 with open('/TopStordata/crons','w') as f:
  f.write(cronstr)
 cmdline='/bin/crontab /TopStordata/crons'
 subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout

if __name__=='__main__':
 etctocron(*sys.argv[1:])
