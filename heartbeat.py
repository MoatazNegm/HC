#!/usr/bin/python3

import sys, os, subprocess
from etcdget import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
from time import sleep
from time import time as stamp

leader, leaderip, myhost, myhostip, nextleader, nextleaderip = '','','','','',''
etcd = ''
dev = 'enp0s8'
os.environ['ETCDCTL_API']= '3'
# every nmap is bounded twice: nmap's own --host-timeout and a subprocess timeout (nmap 7.92 can poll for ever after the
# interface it scans on is removed, e.g. the bond0 rebuild of docker_setup.sh or any 'nmcli conn down/up cmynode')
NMAP = 'nmap --max-rtt-timeout 500ms --host-timeout 5s -n -p '
NMAPTIMEOUT = 15


def dosync(*args):
  global etcd, leader ,leaderip, myhost, myhostip, nextleader, nextleaderip
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 




def splitnext(value):
 # nextlead/er is '<host>/<ip>', written by the leader (see leadernextlead).  Older branches wrote the bare
 # host name; a value without a host in it ('None', '_1', '-1') means there is no next leader.
 value = str(value)
 if 'dhcp' not in value:
  return '', ''
 parts = value.split('/')
 return parts[0], (parts[1] if len(parts) > 1 else '')

def getnextlead():
 # read only: a node never announces itself, the leader names the next leader and syncs it to every node
 global etcd, leader ,leaderip, myhost, myhostip, nextleader, nextleaderip
 nextleader, nextleaderip = splitnext(get(etcd,'nextlead/er')[0])
 if nextleader and not nextleaderip:
  nextleaderip = str(get(etcd,'ready/'+nextleader)[0])
 return nextleader , nextleaderip

readyseen = None

def nodeevent(code, severity, *params):
 # QSD5.352 (QC 707, 605, 681): the leader announces a node that is ready again (a return or a join: Partsu01 'Node <host>
 # completed joining cluster with ip <ip>') and a lost node that was not the leader (Partst02 'Node <host> is down';
 # leaderlost.sh only sent it when the LEADER was lost).  Only the leader sends them, so every event is logged once.
 try:
  subprocess.run(['docker','exec','etcdclient','/TopStor/logmsg.py',code,severity,'system']+[str(p) for p in params],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
 except Exception as e:
  print('node event', code, params, e)

# QSD5.337 (test 646 QX-047 step 3): a peer is declared lost only after HOLDOFF seconds of failed checks in a row (it took ~3-4 s:
# the leader's bond0 re-activations of one NFS address change, ~6 s, made the follower take over while the leader kept running,
# both nodes leader and the pool imported on both). For the leader its own node address (ready/<leader>) is checked as well as
# the cluster address: a leader that answers on its node address is not lost. failsince: peer (or '__localetcd__') -> first
# failure of the current run of failures.
HOLDOFF = 7   # test 680: rounds on a dead peer take ~2.5 s now: lost on the ~4th failed round (~7.5 s), still more than the ~6 s bond blip of test 646
failsince = dict()
# test 683: an nmap started at boot (bond0 still coming up) hung in poll() for over an hour; check_output had no timeout,
# so the heartbeat loop never ran a round and the follower never took over when the leader stopped.  Every nmap/ping
# call has a timeout now (check_output kills the child when it expires).
NMAPSECS = 10

def reachable(ip):
 # nmap on the etcd port (host discovery as root) and, if that does not say up, one ping
 if not ip:
  return False
 try:
  res = subprocess.check_output(['nmap','--max-rtt-timeout','500ms','-n','-p','2379',ip],stderr=subprocess.STDOUT,timeout=15).decode('utf-8')
  if 'Host is up' in res or 'open' in res:
   return True
 except Exception:
  pass
 try:
  subprocess.check_output(['ping','-c','1','-w','1',ip],stderr=subprocess.STDOUT,timeout=5)
  return True
 except Exception:
  return False

def heldoff(key, failed, what):
 # True while a run of failures of <key> is shorter than HOLDOFF (the caller does not act yet); an ok check ends the run
 if not failed:
  failsince.pop(key, None)
  return False
 first = failsince.setdefault(key, stamp())
 if stamp() - first < HOLDOFF:
  print(what, 'failing for', int(stamp() - first), 's, lost only after', HOLDOFF, 's')
  return True
 failsince.pop(key, None)
 with open('/root/heartproblem','a') as f:
  f.write(chr(10)+what+' failed for '+str(int(stamp() - first))+' s in a row'+chr(10))
 return False

def leadernextlead(knowns):
 # LEADER ONLY.  The leader names the next leader: a node that has just become ready, or -- when the
 # current one is not a ready node any more (lost, evacuated, this node itself after a take over, None) --
 # another ready node.  It writes nextlead/er = '<host>/<ip>' and posts the sync request (the request and
 # the leader's own done mark), so the checksyncs looper of every node copies it into its local etcd.
 global etcd, leader ,leaderip, myhost, myhostip, readyseen
 others = [ (k[0].split('/')[1], str(k[1])) for k in knowns if 'ready/' in str(k[0]) and k[0].split('/')[1] != myhost ]
 names = [ o[0] for o in others ]
 new = [] if readyseen is None else [ o for o in others if o[0] not in readyseen ]
 readyseen = set(names)
 for host, ip in new:
  nodeevent('Partsu01', 'info', host, ip)
 if len(others) == 0:
  return
 current = str(get(leaderip,'nextlead/er')[0])
 curhost, curip = splitnext(current)
 if len(new) > 0:
  choice = new[-1]
 elif curhost not in names:
  choice = others[-1]
 else:
  choice = [ o for o in others if o[0] == curhost ][0]
 value = choice[0]+'/'+choice[1]
 if current == value:
  return
 print('next leader is now', value, 'it was', current)
 put(leaderip, 'nextlead/er', value)
 dels(leaderip,'sync/nextlead/Add_er','--prefix')
 dosync('sync/nextlead/Add_er_'+choice[0]+'::'+choice[1]+'/request','nextlead_'+str(stamp()))

def hostlost(host, hostip):
                global etcd, leader ,leaderip, myhost, myhostip, nextleader, nextleaderip
                with open('/root/heartproblem','a') as f:
                        f.write('nmap:\n'+host+' '+hostip)

                stampit = str(stamp())
                port = myport = '2379'
                # from this node's own etcd: asking the lost leader's etcd only waited 2 s for the timeout and returned nothing
                clusterip = get(etcd,'namespace/mgmtip')[0]
                if host == leader:
                    dels(myhostip, 'pools',host)
                    dels(myhostip, 'vol',host)
                    print('leader lost. nextleader is ',nextleader, 'while my host',myhost)
                    nextleader, nextleaderip =  splitnext(get(etcd,'nextlead/er')[0])
                    if nextleader:
                        if not nextleaderip:
                            nextleaderip = myhostip if nextleader == myhost else str(get(etcd,'ready/'+nextleader)[0])
                        leader = nextleader 
                        put(myhostip,'leader',leader)
                    if myhost == nextleader:
                        cmdline='/pace/leaderlost.sh '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+nextleader+' '+nextleaderip+' '+clusterip+' '+host
                        # no timeout on purpose: the take over (docker_primary.sh: pool import, cluster ip, containers)
                        # must not be killed halfway; a half-done take over is worse than a late one
                        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
                        etcd = leaderip
                        dels(leaderip, 'sync/hostdown/'+host,'--prefix')
                        put(leaderip,'sync/hostdown/'+host+'_/request','hostdown_'+stampit)
                        put(leaderip,'sync/hostdown/'+host+'_/request/'+myhost,'hostdown_'+stampit)
                    put(etcd,'refreshdisown/'+myhost,'yes')
                    result='failed'
                    # wait for the cluster ip to answer again, but never for ever: after 5 minutes give up
                    # and go back to the main loop (it used to spin here, without a pause, until a restart)
                    waituntil = stamp() + 300
                    while 'ok' not in str(result):
                        if stamp() > waituntil:
                            print('no leader answers on', leaderip, 'after 5 minutes .... back to the main loop')
                            with open('/root/heartproblem','a') as f:
                                f.write('\nno new leader on '+leaderip+' after 300s\n')
                            break
                        sleep(1)
                        print('chceking new leader')
                        cmdline=NMAP+port+' '+leaderip
                        try:
                            result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT,timeout=NMAPTIMEOUT).decode('utf-8')
                        except Exception:
                            result=''
                        if 'Host is up' in result or 'open' in result:
                            result = (host,'ok')
                        else:
                            result = (host,'lost')
                
                else:
                    dels(leaderip, 'pools',host)
                    if myhost == leader:
                        nodeevent('Partst02', 'warning', host)
                dels(etcd, 'cpuperf/'+host)
                cmdline='/pace/hostlost.sh '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+host
                try:
                        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT,timeout=300).decode('utf-8')
                except subprocess.TimeoutExpired:
                        # a hung hostlost.sh must not freeze failure detection; the membership clean-up below still runs
                        with open('/root/heartproblem','a') as f:
                                f.write('\nhostlost.sh timed out after 300s for '+host+'\n')
                dels(etcd,'ready/',host)
                dels(etcd, 'running/', host)
                dels(etcd, 'host', host)
                dels(etcd, 'known/',host)
                dels(etcd, 'vol',host)
                dels(etcd, 'sync/hostdown',host)


def hostfound(host, hostip):
                """Recovery path: a peer that was previously hostlost() is reachable again.
                Re-publish the four membership keys that hostlost() deletes, and trigger
                the peer's own republish path so its disk/pool records come back too."""
                global etcd, leader ,leaderip, myhost, myhostip
                with open('/root/heartproblem','a') as f:
                        f.write('recovery:\n'+host+' '+hostip+'\n')
                put(etcd, 'ready/'+host, hostip)
                put(etcd, 'known/'+host, hostip)
                put(etcd, 'running/'+host, hostip)
                put(etcd, 'host/'+host, hostip)
                # no /pace/hostfound.sh exists (never did): the returning node's own docker_setup.sh republishes its ready/ key and syncs it
def heartbeat(*args):
    global etcd, leader ,leaderip, myhost, myhostip
    # start-up reads: a hung docker exec raises TimeoutExpired, heartbeat.py exits and heartbeatlooper.sh starts it again
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
    leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,timeout=30).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
    leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,timeout=30).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
    myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,timeout=30).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
    myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,timeout=30).stdout.decode('utf-8').replace('\n','').replace(' ','')
    nochange = 1
    knownsn =  0
    port = myport = '2379'
    if myhost == leader:
        etcd = leaderip
    else:
        etcd = myhostip
    nextleader, nextleaderip = getnextlead()
    while True:
        print('looping')
        sleep(1)
        tries = 0
        while tries < 8:
            knowns = get(etcd, 'ready','--prefix')
            if 'dhcp' in str(knowns):
                tries = 10
                break
            tries +=1
        if len(knowns) == knownsn and knownsn == 1:
            print('only one host is running..,,will do nothing')
            continue
        knownsn = len(knowns)
        if heldoff('__localetcd__', tries < 10, 'ready keys from the local etcd '+str(etcd)):
           continue
        if tries < 10: 
           hostlost(leader, leaderip)
        elif myhost == leader:
           leadernextlead(knowns)

        # Recovery: ActivePartners that are NOT in knowns were hostlost'd earlier.
        # Nmap them and re-publish membership keys if they're reachable again.
        try:
            partners = get(etcd, 'ActivePartners', '--prefix')
            known_hosts = set(known[0].split('/')[1] for known in knowns)
            for partner in partners:
                phost = partner[0].split('/')[1]
                pip = partner[1]
                if phost == myhost or phost in known_hosts:
                    continue
                cmdline='nmap --max-rtt-timeout 500ms -n -p '+port+' '+pip
                res=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT,timeout=NMAPSECS).decode('utf-8')
                if 'Host is up' in res or 'open' in res:
                    hostfound(phost, pip)
        except Exception:
            pass
        for known in knowns:
            host = known[0].split('/')[1]
            if host == myhost:
                continue
            if host == leader:
                hostip = leaderip
            else:
                hostip = known[1]
            print('nmapping')
            result = 'failed'
            tries = 0
            while tries < 2:
                tries +=1
                res = ''
                try:
                    cmdline='nmap --max-rtt-timeout 500ms --host-timeout 1500ms -n -p '+port+' '+hostip   # test 680: a dead peer answers nothing; nmap's own waits made a round ~5 s
                    res=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT,timeout=NMAPSECS).decode('utf-8')
                except:
                    result=(host,'doubt')
                if 'Host is up' in res or 'open' in res:
                    result = (host,'ok')
                else:
                    result = (host,'doubt')
                if 'doubt' in str(result):
                    print('ddddddddddddddddddddddddd')
                    cmdline='ping -w 1 '+hostip 
                    print(cmdline)
                    try:
                        subprocess.check_output(cmdline.split(),timeout=5)
                    except Exception:
                        result=(host,'lost')
                if 'ok' in str(result):
                    break
                # test 680: no port and no ping answer: this round is over (the second try and its 1 s sleep made a round on a
                # dead peer ~5 s; HOLDOFF counts from the first failed round, so detection took ~15 s)
                if 'lost' in str(result):
                    break
                sleep(1)
            print(result)
            if result[1] == 'doubt':
                # nmap gave no answer but ping did (in the last try): the host is alive, do not declare it lost
                # (a local nmap problem must never start a take over of a live leader); it is checked again next loop
                print('nmap doubt but ping answers', host, hostip)
                heldoff(host, False, 'host '+host+' '+hostip)   # alive: ends a run of failures (merge M+A)
                continue
            if 'ok' not in str(result) and host == leader and str(known[1]) not in ('', leaderip):
                if reachable(str(known[1])):
                    print('leader',host,'does not answer on',leaderip,'but on its node address',known[1],': not lost')
                    result = (host,'ok on node address')
            if heldoff(host, 'ok' not in str(result), 'host '+host+' '+hostip):
                continue
            if 'ok' not in str(result):
                with open('/root/heartproblem','a') as f:
                        f.write('OK:\n'+host+' '+res)
                hostlost(host, hostip)
                break
    print(leader ,leaderip, myhost, myhostip)
    return leader ,leaderip, myhost, myhostip

 


if __name__=='__main__':

 print(leader ,leaderip, myhost, myhostip)
 heartbeat(*sys.argv)
