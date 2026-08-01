#!/bin/bash
# creates a direct veth link (host vm <-> each proxy container) for centralized
# log forwarding, independent of docker's bridge network. uses the same raw
# veth+netns mechanism the rest of the mini-internet uses for all its links

# what mode to run in - "check" just looks and reports, "apply" makes real changes
MODE="${1:-check}"

# every group number we need to set this up for
GROUP_LIST="1 2 3 4 5 6 7 8 9 10"

# main loop - do everything below once for every group
for g in $GROUP_LIST; do
    PROXY="${g}_ssh"

    # skip this group entirely if its proxy container doesn't even exist
    sudo docker inspect "$PROXY" > /dev/null 2>&1 || { echo "[$PROXY] does not exist, skipping"; continue; }

    # check whether the direct link already exists on this proxy
    HAS_LINK=$(sudo docker exec "$PROXY" sh -c "ip addr show hostlink 2>/dev/null" || true)

    # check mode - just report what's needed, don't change anything
    if [ "$MODE" == "check" ]; then
        if [ -z "$HAS_LINK" ]; then
            echo "[$PROXY] NEEDS centralized connector"
        else
            echo "[$PROXY] connector present"
        fi
        continue
    fi

    # apply mode - actually build the real connection
    if [ "$MODE" == "apply" ]; then
        if [ -n "$HAS_LINK" ]; then
            # already set up, nothing to do here
            echo "[$PROXY] already present, skipping"
            continue
        fi

        # get this container's actual process id, since network namespaces
        # are tied to a specific process, not the container name itself
        PID=$(sudo docker inspect -f "{{.State.Pid}}" "$PROXY")

        # give ourselves a way to reference this container's network namespace
        # by its process id, so later "ip netns" commands know where to go
        sudo mkdir -p /var/run/netns
        sudo ln -sf /proc/$PID/ns/net /var/run/netns/$PID

        # create the actual virtual cable - two ends, linked to each other
        sudo ip link add "hostlink_g${g}" type veth peer name "proxylink_g${g}"

        # give the host's end of the cable its own private address, and turn it on
        sudo ip addr add "10.200.${g}.1/30" dev "hostlink_g${g}"
        sudo ip link set "hostlink_g${g}" up

        # move the other end of the cable into the proxy container's own network space
        sudo ip link set "proxylink_g${g}" netns $PID
        # rename it inside the container to something simple and consistent
        sudo ip netns exec $PID ip link set dev proxylink_g${g} name hostlink
        # give the proxy's end of the cable its own private address, and turn it on
        sudo ip netns exec $PID ip addr add "10.200.${g}.2/30" dev hostlink
        sudo ip netns exec $PID ip link set hostlink up

        # point this proxy's log forwarding at the new direct link instead of
        # docker's shared bridge network
        sudo docker exec "$PROXY" sh -c "sed -i 's|target=\"172.17.0.1\"|target=\"10.200.${g}.1\"|' /etc/rsyslog.conf"
        # restart rsyslog so the new setting actually takes effect
        sudo docker exec "$PROXY" sh -c "pkill rsyslogd; sleep 1; rsyslogd"

        # confirm the link genuinely exists now, and report the real result
        VERIFY=$(sudo docker exec "$PROXY" sh -c "ip addr show hostlink 2>/dev/null" || true)
        if [ -n "$VERIFY" ]; then
            echo "[$PROXY] OK — connector created, rsyslog repointed to 10.200.${g}.1"
        else
            echo "[$PROXY] FAILED"
        fi
    fi
done
