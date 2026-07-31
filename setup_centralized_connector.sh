#!/bin/bash
# Creates a direct veth link (host VM <-> each proxy container) for centralized
# log forwarding, independent of Docker's bridge network. Uses the same raw
# veth+netns mechanism the rest of the mini-internet uses for all its links.

MODE="${1:-check}"
GROUP_LIST="1 2 3 4 5 6 7 8 9 10"

for g in $GROUP_LIST; do
    PROXY="${g}_ssh"
    sudo docker inspect "$PROXY" > /dev/null 2>&1 || { echo "[$PROXY] does not exist, skipping"; continue; }

    HAS_LINK=$(sudo docker exec "$PROXY" sh -c "ip addr show hostlink 2>/dev/null" || true)

    if [ "$MODE" == "check" ]; then
        if [ -z "$HAS_LINK" ]; then
            echo "[$PROXY] NEEDS centralized connector"
        else
            echo "[$PROXY] connector present"
        fi
        continue
    fi

    if [ "$MODE" == "apply" ]; then
        if [ -n "$HAS_LINK" ]; then
            echo "[$PROXY] already present, skipping"
            continue
        fi

        PID=$(sudo docker inspect -f "{{.State.Pid}}" "$PROXY")
        sudo mkdir -p /var/run/netns
        sudo ln -sf /proc/$PID/ns/net /var/run/netns/$PID

        sudo ip link add "hostlink_g${g}" type veth peer name "proxylink_g${g}"
        sudo ip addr add "10.200.${g}.1/30" dev "hostlink_g${g}"
        sudo ip link set "hostlink_g${g}" up

        sudo ip link set "proxylink_g${g}" netns $PID
        sudo ip netns exec $PID ip link set dev proxylink_g${g} name hostlink
        sudo ip netns exec $PID ip addr add "10.200.${g}.2/30" dev hostlink
        sudo ip netns exec $PID ip link set hostlink up

        sudo docker exec "$PROXY" sh -c "sed -i 's|target=\"172.17.0.1\"|target=\"10.200.${g}.1\"|' /etc/rsyslog.conf"
        sudo docker exec "$PROXY" sh -c "pkill rsyslogd; sleep 1; rsyslogd"

        VERIFY=$(sudo docker exec "$PROXY" sh -c "ip addr show hostlink 2>/dev/null" || true)
        if [ -n "$VERIFY" ]; then
            echo "[$PROXY] OK — connector created, rsyslog repointed to 10.200.${g}.1"
        else
            echo "[$PROXY] FAILED"
        fi
    fi
done
