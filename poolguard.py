#!/usr/bin/python3
"""poolguard: is a pool being (or just) deleted?  (tests 676, 678)

DGdestroyPool writes pooldeleting/<pool> = <epoch> when a delete starts and leaves it for DELETEDSECS after the destroy:
the loops that (re)write pools/<pool> and poolnxt/<pool> (putzpool, selectimport, zpooltoimport) work from a cluster view
that can be a few minutes old and put the deleted pool's keys back (seen: pools/ and poolnxt/ back 2-6 min after a delete).
"""
from time import time
from etcdgetpy import etcdget as get

DELETEDSECS = 30*24*3600   # test 679: 15 min was too short, an OFFLINE leg (label not cleared by the destroy) was imported later

def deletingpools(leaderip):
    """the names of the pools deleted (or being deleted) in the last DELETEDSECS seconds"""
    names = set()
    now = time()
    for x in get(leaderip, 'pooldeleting/', '--prefix'):
        if not isinstance(x, (tuple, list)) or len(x) < 2:
            continue
        name = str(x[0]).replace('pooldeleting/', '')
        try:
            age = now - float(x[1])
        except (TypeError, ValueError):
            age = 0          # an old 'yes' marker: still being deleted
        if age < DELETEDSECS:
            names.add(name)
    return names
