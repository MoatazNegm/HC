#!/bin/bash

leaderip="$1"
myhost="$2"

# Get current dnssearch entries from etcd
entries=$(/pace/etcdget.py "$leaderip" dnssearch --prefix | awk -F"'" '{print $4}')

for hostname in $entries; do
    # Resolve hostname to IP
    ip=$(getent ahosts "$hostname" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 | awk '{print $1}')

    if [ -n "$ip" ]; then
        # Check if correct entry already exists in container
        if ! docker exec flask grep -qE "^$ip\s+$hostname(\s|$)" /etc/hosts; then
            echo "Adding or updating $hostname -> $ip in flask /etc/hosts"
            # Remove any old entries for this hostname
            docker exec flask sed -i "/\s$hostname(\s|$)/d" /etc/hosts
            # Add the new entry
            docker exec flask bash -c "echo '$ip    $hostname' >> /etc/hosts"
        fi
    else
        echo "Could not resolve $hostname"
    fi
done

