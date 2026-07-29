#!/bin/bash
# Deploys rsyslog everywhere with group-aware relay:
# proxies (*_ssh) get apk-installed rsyslog, listen on udp:514, forward to host VM.
# routers/hosts get binary-copied rsyslog, forward to THEIR OWN GROUP's proxy.

MODE="${1:-check}"
GATEWAY="172.17.0.1"
BUILD_SOURCE="3_ssh"   # has a working from-source-independent rsyslog (via apk) to clone from

TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "(host[0-9]*$|router$|^[0-9]+_ssh$)")

get_group() {
    echo "$1" | grep -oE '^[0-9]+'
}

install_rsyslog_binary_copy() {
    local c="$1"
    local TMPDIR
    TMPDIR=$(mktemp -d)
    for f in libz.so.1 libestr.so.0 libfastjson.so.4 libuuid.so.1; do
        sudo docker exec "$BUILD_SOURCE" sh -c "cat /usr/lib/$f 2>/dev/null || cat /lib/$f 2>/dev/null" > "$TMPDIR/$f"
        cat "$TMPDIR/$f" | sudo docker exec -i "$c" sh -c "cat > /usr/lib/$f 2>/dev/null || cat > /lib/$f"
    done
    sudo docker exec "$BUILD_SOURCE" cat /usr/sbin/rsyslogd > "$TMPDIR/rsyslogd"
    cat "$TMPDIR/rsyslogd" | sudo docker exec -i "$c" sh -c "cat > /usr/sbin/rsyslogd && chmod +x /usr/sbin/rsyslogd"
    sudo docker exec "$BUILD_SOURCE" tar -C /usr/lib -cf - rsyslog 2>/dev/null | sudo docker exec -i "$c" tar -C /usr/lib -xf - 2>/dev/null
    sudo docker exec "$BUILD_SOURCE" tar -C /etc -cf - rsyslog.conf 2>/dev/null | sudo docker exec -i "$c" tar -C /etc -xf - 2>/dev/null
    sudo docker exec "$c" mkdir -p /var/lib/rsyslog
    sudo rm -rf "$TMPDIR"
}

for c in $TARGETS; do
    GROUP=$(get_group "$c")
    IS_PROXY=false
    [[ "$c" == *_ssh ]] && IS_PROXY=true

    if [ "$IS_PROXY" = true ]; then
        FORWARD_TARGET="$GATEWAY"
    else
        FORWARD_TARGET="158.${GROUP}.0.2"
    fi

    HAS_RSYSLOG=$(sudo docker exec "$c" sh -c "command -v rsyslogd" 2>/dev/null)

    if [ "$MODE" == "check" ]; then
        if [ -z "$HAS_RSYSLOG" ]; then
            echo "[$c] NEEDS rsyslog (group $GROUP, forward->$FORWARD_TARGET)"
        else
            echo "[$c] rsyslog present (group $GROUP, forward->$FORWARD_TARGET)"
        fi
        continue
    fi

    if [ "$MODE" == "apply" ]; then
        if [ -z "$HAS_RSYSLOG" ]; then
            if [ "$IS_PROXY" = true ]; then
                echo "[$c] apk installing rsyslog..."
                sudo docker exec "$c" apk add --no-cache rsyslog
            else
                echo "[$c] binary-copy installing rsyslog from $BUILD_SOURCE..."
                install_rsyslog_binary_copy "$c"
            fi
        fi

        sudo docker exec "$c" sh -c "sed -i 's|^module(load=\"imklog\")|#module(load=\"imklog\")|' /etc/rsyslog.conf"

        if [ "$IS_PROXY" = true ]; then
            sudo docker exec "$c" sh -c "grep -q 'imudp' /etc/rsyslog.conf || echo 'module(load=\"imudp\") input(type=\"imudp\" port=\"514\")' >> /etc/rsyslog.conf"
        fi

        sudo docker exec "$c" sh -c "grep -qxF 'authpriv.* @${FORWARD_TARGET}:514' /etc/rsyslog.conf || echo 'authpriv.* @${FORWARD_TARGET}:514' >> /etc/rsyslog.conf"
        sudo docker exec "$c" sh -c "mkdir -p /var/lib/rsyslog; pkill rsyslogd 2>/dev/null; sleep 1; rsyslogd"

        sudo docker exec "$c" sh -c "grep -q '\"writer\" : \"syslog\"' /etc/tlog/tlog-rec-session.conf 2>/dev/null || sed -i 's|\"writer\" : \"file\"|\"writer\" : \"syslog\"|' /etc/tlog/tlog-rec-session.conf 2>/dev/null"

        RUNNING=$(sudo docker exec "$c" sh -c "pgrep rsyslogd" 2>/dev/null)
        if [ -n "$RUNNING" ]; then
            echo "[$c] OK — rsyslog running, forwarding to $FORWARD_TARGET, tlog writer=syslog"
        else
            echo "[$c] FAILED — rsyslogd not running"
        fi
    fi
done
