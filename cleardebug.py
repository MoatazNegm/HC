#!/bin/python3.6
import subprocess,sys
from etcdget import etcdget as get
from threading import Thread
from etcdgetlocal import etcdget as getlocal
from ast import literal_eval as mtuple
from socket import gethostname as hostname


debugwords=['newtime', 'origtime', 'newtime', 'basetime','timing']
thefile=sys.argv[1]
with open(thefile,'r') as thef:
 with open(thefile+'.debug','w') as nfile:
  nfile.writelines(thef.readlines())
with open(thefile+'.debug','r') as thef:
 with open(thefile,'w') as nfile:
  for l in thef:
   print('l=',l)
   if not any(x in l for x in debugwords):
    nfile.write(l) 
