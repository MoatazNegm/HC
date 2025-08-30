#!/bin/bash

# Usage: retryvolumedelete.sh <leaderip> <myhost>

leaderip=$1
myhost=$2

MAX_RETRIES=3
RETRY_DELAY=5
LOG_PREFIX="VOLDELRETRY"

log_message() {
    local msg=$2
    echo "[$(date)] [$level] $msg"
    docker exec etcdclient /TopStor/logmsg.py ${LOG_PREFIX}001 $level $userreq "$msg"
}

find_stop_blocking_containers() {
    local volume_path="$pDG/$volname"
    log_message "info" "Looking for $service_type containers blocking $volume_path"
    container_list=$(docker ps --format "{{.Names}}" | grep -i "$service_type")

    if [ -z "$container_list" ]; then
        log_message "info" "No containers found matching $service_type"
        return 1
    fi

    while IFS= read -r cname; do
        if docker inspect "$cname" 2>/dev/null | grep -q "$volname"; then
            log_message "info" "Stopping blocking container: $cname"
            if docker stop "$cname" >/dev/null 2>&1; then
                log_message "info" "Successfully stopped container: $cname"
                return 0
            else
                log_message "error" "Failed to stop container: $cname"
                return 1
                return 1
            fi
        fi
    done <<< "$container_list"

    log_message "info" "No containers blocking the volume were found"
    return 1
}

attempt_volume_deletion() {
    local volume_path="$pDG/$volname"
    log_message "info" "Unmounting and destroying volume: $volume_path"
    /sbin/zfs unmount -f "$volume_path" 2>/dev/null
    /sbin/zfs destroy -rf "$volume_path" 2>/dev/null
    return $?
}


entry=$(/pace/etcdget.py "$leaderip" "cVolToDelete/$myhost")

if [[ "$entry" == "_1" || -z "$entry" ]]; then
    exit 0
fi

IFS="|" read -r pDG volname userreq caller_script <<< "$entry"

if [[ -z "$pDG" || -z "$volname" ]]; then
    log_message "error" "Malformed etcd entry: $entry"
    exit 1
fi

log_message "info" "Detected deletion task: $pDG/$volname requested by $userreq"

# Determine service type from caller_script
service_type=""
case "$caller_script" in
    *CIFS*) service_type="CIFS" ;;
    *NFS*) service_type="NFS" ;;
    *ISCSI*) service_type="ISCSI" ;;
    *HOME*) service_type="HOME" ;;
esac


retry_count=0

while [ $retry_count -lt $MAX_RETRIES ]; do

    # Check if etcd key still exists
    entry=$(/pace/etcdget.py "$leaderip" "cVolToDelete/$myhost")
    if [[ "$entry" == "_1" ]]; then
        log_message "info" "No etcd key found — aborting retry"
        exit 0
    fi

    find_stop_blocking_containers

    if attempt_volume_deletion; then
        log_message "info" "Volume deleted: $pDG/$volname from host $myhost"
        /pace/etcddel.py "$leaderip" "cVolToDelete/$myhost"
        exit 0
    else
        log_message "warn" "Deletion failed (attempt $((retry_count + 1))/$MAX_RETRIES)"
    fi

    retry_count=$((retry_count + 1))
    sleep $RETRY_DELAY
done

log_message "error" "Volume deletion failed after $MAX_RETRIES attempts"
exit 1

