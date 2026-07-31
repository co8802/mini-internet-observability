#!/bin/bash
# deploys rsyslog everywhere with group-aware relay:
# proxies (*_ssh) get apk-installed rsyslog (genuine independent install), listen on udp:514, forward to host vm.
# routers/hosts unpack rsyslog from a bundled tarball (bundles/rsyslog_bundle.tar) - self-contained,
# not live-copied from any specific container - forward to their own group's proxy

# what mode to run in - "check" just looks and reports, "apply" makes real changes
MODE="${1:-check}"

# the host vm's docker bridge address - what proxies forward their logs to
GATEWAY="172.17.0.1"

# path to the pre-built rsyslog bundle - what routers/hosts unpack from,
# since they have no internet access to install anything themselves
BUNDLE="$HOME/mini-internet-observability/bundles/rsyslog_bundle.tar"

# get every container we care about: hosts, routers, and proxies
TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "(host[0-9]*$|router$|^[0-9]+_ssh$)")

# pulls the group number out of a container's name (e.g. "4_ATLrouter" -> "4")
get_group() {
    echo "$1" | grep -oE '^[0-9]+'
}

# reusable steps for installing rsyslog from the bundle onto a container with no internet
install_rsyslog_from_bundle() {
    local c="$1"  # the container's name, passed in when this function is called
    # unpack every file from the bundle straight onto the container's real filesystem
    cat "$BUNDLE" | sudo docker exec -i "$c" tar -C / -xf -
    # rsyslog needs this folder to exist for its own internal working files
    sudo docker exec "$c" mkdir -p /var/lib/rsyslog
}

# main loop - do everything below once for every container in our list
for c in $TARGETS; do
    # figure out which group this container belongs to
    GROUP=$(get_group "$c")

    # assume this container is not a proxy until we check otherwise
    IS_PROXY=false
    # if the container's name ends in "_ssh", it is a proxy - flip the flag
    [[ "$c" == *_ssh ]] && IS_PROXY=true

    # proxies forward straight to the host vm. routers/hosts forward to
    # their own group's proxy instead, since they can't reach the host vm directly
    if [ "$IS_PROXY" = true ]; then
        FORWARD_TARGET="$GATEWAY"
    else
        FORWARD_TARGET="158.${GROUP}.0.2"
    fi

    # check whether rsyslog is already installed on this container
    HAS_RSYSLOG=$(sudo docker exec "$c" sh -c "command -v rsyslogd" 2>/dev/null)

    # check mode - just report what's needed, don't change anything
    if [ "$MODE" == "check" ]; then
        if [ -z "$HAS_RSYSLOG" ]; then
            echo "[$c] NEEDS rsyslog (group $GROUP, forward->$FORWARD_TARGET)"
        else
            echo "[$c] rsyslog present (group $GROUP, forward->$FORWARD_TARGET)"
        fi
        continue
    fi

    # apply mode - actually make the real changes
    if [ "$MODE" == "apply" ]; then
        # if rsyslog isn't installed yet, install it the right way for this container type
        if [ -z "$HAS_RSYSLOG" ]; then
            if [ "$IS_PROXY" = true ]; then
                # proxies have real internet access, so a normal package install works
                echo "[$c] apk installing rsyslog..."
                sudo docker exec "$c" apk add --no-cache rsyslog
            else
                # routers/hosts have no internet access, so unpack the bundle instead
                echo "[$c] installing rsyslog from bundle..."
                install_rsyslog_from_bundle "$c"
            fi

            # check again now that we just tried installing it
            HAS_RSYSLOG=$(sudo docker exec "$c" sh -c "command -v rsyslogd" 2>/dev/null)
            if [ -z "$HAS_RSYSLOG" ]; then
                # still missing after trying to install it - something went wrong
                echo "[$c] INSTALL FAILED — skipping config"
                continue
            fi
        fi

        # disable kernel-log reading - containers don't have permission for this,
        # and we don't need it anyway since we only care about tlog's own recordings
        sudo docker exec "$c" sh -c "sed -i 's|^module(load=\"imklog\")|#module(load=\"imklog\")|' /etc/rsyslog.conf"

        # proxies also need to LISTEN for incoming logs from their own group's
        # routers/hosts, so turn on the udp-listening module - but only if it
        # isn't already turned on
        if [ "$IS_PROXY" = true ]; then
            sudo docker exec "$c" sh -c "grep -q 'imudp' /etc/rsyslog.conf || echo 'module(load=\"imudp\") input(type=\"imudp\" port=\"514\")' >> /etc/rsyslog.conf"
        fi

        # add the actual forwarding rule - send anything tagged "authpriv" (which is
        # what tlog uses) onward to this container's correct target, but only if
        # that exact rule isn't already there
        sudo docker exec "$c" sh -c "grep -qxF 'authpriv.* @${FORWARD_TARGET}:514' /etc/rsyslog.conf || echo 'authpriv.* @${FORWARD_TARGET}:514' >> /etc/rsyslog.conf"

        # make sure rsyslog's working folder exists, then restart it so all
        # our config changes actually take effect
        sudo docker exec "$c" sh -c "mkdir -p /var/lib/rsyslog; pkill rsyslogd 2>/dev/null; sleep 1; rsyslogd"

        # make sure tlog is set to send its recordings through syslog rather than
        # just saving them to a local file, so they actually get forwarded
        sudo docker exec "$c" sh -c "grep -q '\"writer\" : \"syslog\"' /etc/tlog/tlog-rec-session.conf 2>/dev/null || sed -i 's|\"writer\" : \"file\"|\"writer\" : \"syslog\"|' /etc/tlog/tlog-rec-session.conf 2>/dev/null"

        # confirm rsyslog is actually running right now, and report the real result
        RUNNING=$(sudo docker exec "$c" sh -c "pgrep rsyslogd" 2>/dev/null)
        if [ -n "$RUNNING" ]; then
            echo "[$c] OK — rsyslog running, forwarding to $FORWARD_TARGET, tlog writer=syslog"
        else
            echo "[$c] FAILED — rsyslogd not running"
        fi
    fi
done
