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

LOGF = '/root/etctocron.log'

def log(msg):
 try:
  with open(LOGF, 'a') as f:
   f.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+msg+'\n')
 except Exception:
  pass

def _etctocron(leaderip, period='--prefix'):
 # QSD5.352 r10f (QC proof 10e D14, high): the table is read as TEXT.  It was read as str(bytes) with "b'" cut off: once the
 # table held a single quote (the r10e guardian cron line  pgrep -f '^/bin/bash ...'), Python printed the bytes as b"...",
 # the first line kept 'b"' in front of its minute field, crontab refused the whole new table ("bad minute", the error went
 # nowhere) and the node kept its old table.  So a node had schedule lines only where SnapshotCreate* wrote them itself (the
 # pool owner): the leader, the only node whose putcron.sh posts the call, had none, and no scheduled snapshot fired while
 # the owner was not the leader.  A record that is no schedule is skipped (it raised IndexError and ended the sync pass),
 # and the result of the install is logged in /root/etctocron.log.
 cmdline='/bin/crontab -l'
 crons=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode('utf-8','replace')
 crons=[x for x in crons.split('\n') if 'nowhost' not in x and len(x) > 5 ]
 cronstr=''
 for x in crons:
  cronstr+=x+'\n'
 etccron=get(leaderip,'Snapperiod',period)
 nlines=0
 for x in etccron:
  try:
   cronid = str(x[0].split('/')[4])
   yleft=str(x[1].split('/TopStor')[0].replace('%',' '))
   yright=x[1].split('/TopStor')[1].replace('%',' ')
  except (IndexError, TypeError, AttributeError):
   if x not in ('_1', '-1'):
    log('not a schedule record, skipped: '+str(x)[:200])
   continue
  cronstr += yleft+' /TopStor/putcron.sh /TopStor/etcdput.py '+leaderip+' call/'+cronid+' /TopStor'+yright.replace(' ','::')+'\n'
  nlines+=1
 print(cronstr)
 with open('/TopStordata/crons','w') as f:
  f.write(cronstr)
 cmdline='/bin/crontab /TopStordata/crons'
 res=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if res.returncode != 0:
  log('crontab refused the new table ('+str(nlines)+' schedule lines), the old table stays: '+res.stderr.decode('utf-8','replace').strip().replace('\n',' | '))
 else:
  log('table installed, '+str(nlines)+' schedule lines')

if __name__=='__main__':
 etctocron(*sys.argv[1:])
