#!/bin/python3.6
with open('zpool.txt') as f:
     read_data = f.read()
     y = read_data.split("\n")
raidtypes=['mirror','raidz','stripe']
raid2=['log','cache','spare']
zpool=[]
for a in y:
