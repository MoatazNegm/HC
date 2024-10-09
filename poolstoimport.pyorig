#!/usr/bin/python3
import subprocess

def getpoolstoimport():
 cmdline='/sbin/zpool import'
 result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
 pools = [ (x.split(': ')[1],result[result.index(x)+1].split(': ')[1]) for x in result if 'pool: pdhcp' in x]
 return pools 

if __name__=='__main__':
 getpoolstoimport()
