#!/usr/bin/python3
"""diskguard: refuse to give a disk that belongs to ANOTHER pool to an automatic replace/attach (test 674 step 6).

While its owner node was down, the test pool P1 was not imported on the surviving node and its disks looked free there:
selectspare ran `zpool replace -f pdhcp588910935 dm-1 <P1 disk>` (the -f also overrides ZFS's own "is part of exported
pool" refusal), so one disk ended up in two pools and both were damaged.  A disk whose ZFS label names a pool other than
the one being healed is not a spare.
"""
import subprocess

def labelinfo(disk):
    """(pool name, pool_guid) pairs from the ZFS labels of disk: whole disk and its first partition."""
    base = disk if disk.startswith('/dev/') else '/dev/disk/by-id/'+disk
    if not disk.startswith('/dev/') and (disk.startswith('dm-') or disk.startswith('sd')):
        base = '/dev/'+disk
    pairs = set()
    for dev in (base, base+'-part1', base+'1'):
        try:
            out = subprocess.run(['/sbin/zdb', '-l', dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20).stdout.decode('utf-8', 'replace')
        except Exception:
            continue
        name = guid = ''
        for line in out.split(chr(10)):
            line = line.strip()
            if line.startswith('name:') and not name:
                name = line.split(':', 1)[1].strip().strip("'")
            elif line.startswith('pool_guid:') and not guid:
                guid = line.split(':', 1)[1].strip()
        if name:
            pairs.add((name, guid))
    return pairs

def liveguids(leaderip):
    """pool guids that are alive: imported on this node, or recorded as ActPool/<pool> in the cluster etcd at leaderip.
    None when the cluster etcd cannot be read: the caller then treats every label as a live pool (the safe side)."""
    guids = set()
    try:
        out = subprocess.run(['/sbin/zpool', 'get', '-H', '-o', 'value', 'guid'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20).stdout.decode()
        guids.update(x.strip() for x in out.split() if x.strip())
    except Exception:
        pass
    if not leaderip or str(leaderip) in ('_1', '-1'):
        return None
    try:
        from etcdgetpy import etcdget as get
        act = [ k for k in get(leaderip, 'ActPool', '--prefix') if isinstance(k, (tuple, list)) and len(k) > 1 ]
    except Exception:
        return None
    if not act:
        return None
    for k in act:
        guids.add(str(k[1]).strip())
    return guids

def labelpools(disk):
    """The pool names in the ZFS labels of disk (by-id name, /dev path or dm name): whole disk and its first partition."""
    base = disk if disk.startswith('/dev/') else '/dev/disk/by-id/'+disk
    if not disk.startswith('/dev/') and (disk.startswith('dm-') or disk.startswith('sd')):
        base = '/dev/'+disk
    names = set()
    for dev in (base, base+'-part1', base+'1'):
        try:
            out = subprocess.run(['/sbin/zdb', '-l', dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20).stdout.decode('utf-8', 'replace')
        except Exception:
            continue
        for line in out.split('\n'):
            line = line.strip()
            if line.startswith('name:'):
                names.add(line.split(':', 1)[1].strip().strip("'"))
    return names

def foreignpool(disk, poolname, leaderip=None):
    """The name of another LIVE pool that disk belongs to, or '' when it is free, already this pool's, or only carries a dead
    label (test 680: a stale label of an old copy of pdhcp588910935, other pool_guid, blocked every replace and the pool
    stayed degraded).  A label counts when its pool_guid is imported here or recorded in ActPool/ of the cluster."""
    pairs = [ (n, g) for n, g in labelinfo(disk) if n and n != poolname ]
    if not pairs:
        return ''
    live = liveguids(leaderip)
    if live is None:
        return sorted(n for n, g in pairs)[0]       # the cluster's pools cannot be read: every label counts
    # test 14 step 13: a pool the cluster still lists (pools/ or poolnxt/) but whose ActPool/ key is missing here is NOT dead:
    # its ActPool never reached this node (created while it was down).  Only a label whose pool name HAS an ActPool entry
    # with another guid is a stale leg (test 680).
    actnames, listed = knownpools(leaderip)
    others = sorted(n for n, g in pairs if not g or g in live or (n not in actnames and n in listed))
    return others[0] if others else ''

def knownpools(leaderip):
    """(names with an ActPool/ entry, names listed in pools/ or poolnxt/) in the cluster etcd at leaderip."""
    actnames, listed = set(), set()
    try:
        from etcdgetpy import etcdget as get
        for key, names in (('ActPool', actnames), ('pools', listed), ('poolnxt', listed)):
            for k in get(leaderip, key, '--prefix'):
                if isinstance(k, (tuple, list)) and len(k) > 1 and str(k[0]).startswith(key+'/'):
                    names.add(str(k[0]).split('/', 1)[1])
    except Exception:
        pass
    return actnames, listed
