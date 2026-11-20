#!/usr/bin/python3
import subprocess,sys, datetime, time, os
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

def iscontainer():
 # the container flavour (as pace/heartbeat.py): the r10r checked reads apply there only
 return os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv') or os.path.isdir('/sys/class/net/eth10')

LOGF = '/root/etctocron.log'
READTRIES = 3
READSTEP = 2
READTMO = 20

def _callid(line):
 # the record id of a schedule line ('... /TopStor/etcdput.py <ip> call/<id> ...'), '' when none
 for w in line.split():
  if w.startswith('call/'):
   return w[5:]
 return ''

def schedids(records):
 # the ids of the schedule records of a read (the 5th key part, as the table build below)
 ids = set()
 for x in records:
  try:
   if '/TopStor' in str(x[1]):
    ids.add(str(x[0].split('/')[4]))
  except (IndexError, TypeError, AttributeError):
   pass
 return ids

def readrecords(ip, period='--prefix', tries=None):
 """(True, [(key, value), ...]) of the Snapperiod records at ip (a period other than '--prefix' keeps the records that
 name it, as etcdget did); (False, []) when etcdctl failed every try: no answer is not the same as no records."""
 for n in range(tries or READTRIES):
  if n:
   time.sleep(READSTEP)
  try:
   r = subprocess.run(['timeout', str(READTMO), 'etcdctl', '--endpoints=http://'+str(ip)+':2379', 'get', 'Snapperiod', '--prefix'],
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, ETCDCTL_API='3'))
  except Exception:
   continue
  if r.returncode != 0:
   continue
  out = r.stdout.decode('utf-8', 'replace')
  if out.endswith('\n'):
   out = out[:-1]
  lines = out.split('\n') if out != '' else []
  recs = list(zip(lines[0::2], lines[1::2]))
  if period != '--prefix':
   recs = [x for x in recs if period in str(x)]
  return True, recs
 return False, []

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
 # QSD5.352 r10r (QC proof 10q S-3, x2 575.4): the schedule lines of the Hourly and Minutely snapshots were lost on a node
 # and the node kept a short table (zfs1 /root/etctocron.log 'table installed, 1 schedule lines' while the leader held 4
 # records).  Cause: every 'nowhost' (schedule) line was dropped FIRST, then the records were read with etcdget, whose
 # '--prefix' read gives [] when etcdctl itself fails (timeout or no answer under load: the return code is not looked
 # at), so a failed read installed a table without the schedules.  Now: the records are read with the etcdctl return
 # code checked (READTRIES tries, READSTEP s apart); a failed read keeps the whole old table ('read failed ... the old
 # table stays'); a working read that has FEWER schedules than the table is read once more and installed only when the
 # second read gives the same records (a real delete), else the old table stays.  /pace/leaderlost.sh runs this once
 # on the new leader after a take-over (the table there was never rebuilt).
 cmdline='/bin/crontab -l'
 crons=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode('utf-8','replace')
 # r10r (validator G-2): checked reads in the CONTAINER flavour only; the physical flavour keeps the old path exactly
 # (drop the schedule lines, then one etcdget read).
 ctr = iscontainer()
 if ctr:
  oldsched=set(_callid(x) for x in crons.split('\n') if 'nowhost' in x and len(x) > 5)
  oldsched.discard('')
  ok, etccron = readrecords(leaderip, period)
  if not ok:
   log('Snapperiod read failed on '+str(leaderip)+' ('+str(READTRIES)+' tries), the old table stays ('+str(len(oldsched))+' schedule lines)')
   return
  if len(schedids(etccron)) < len(oldsched):
   time.sleep(READSTEP)
   ok2, again = readrecords(leaderip, period, 1)
   if not ok2 or schedids(again) != schedids(etccron):
    log('Snapperiod read on '+str(leaderip)+' gave '+str(len(schedids(etccron)))+' schedules, the table has '+str(len(oldsched))+'; not confirmed by a second read ('+('failed' if not ok2 else str(len(schedids(again))))+'), the old table stays')
    return
   log('Snapperiod read on '+str(leaderip)+' confirmed: '+str(len(schedids(etccron)))+' schedules, the table had '+str(len(oldsched))+' (deleted ones go)')
 crons=[x for x in crons.split('\n') if 'nowhost' not in x and len(x) > 5 ]
 cronstr=''
 for x in crons:
  cronstr+=x+'\n'
 if not ctr:
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
