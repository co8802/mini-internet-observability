#!/bin/bash
# Enables automatic tlog recording at login on every proxy container.
# Genuinely self-contained: unpacks from a bundled tarball (bundles/tlog_bundle.tar)
# rather than live-copying from any already-configured container.

LOGFILE=~/tlog_deploy_rollback.log
MODE="${1:-check}"
BUNDLE="$HOME/mini-internet-observability/bundles/tlog_bundle.tar"

TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "^[0-9]+_ssh$")

install_tlog_from_bundle() {
    local c="$1"
    cat "$BUNDLE" | sudo docker exec -i "$c" tar -C / -xf -
    sudo docker exec "$c" sh -c "touch /var/run/utmp && chown root:utmp /var/run/utmp && chmod 664 /var/run/utmp"
}

for c in $TARGETS; do
    HAS_TLOG=$(sudo docker exec "$c" sh -c "command -v tlog-rec-session" 2>/dev/null)

    if [ -z "$HAS_TLOG" ]; then
        if [ "$MODE" == "check" ]; then
            echo "[$c] NEEDS INSTALL"
            continue
        fi
        if [ "$MODE" == "apply" ]; then
            echo "[$c] Installing tlog from bundle..."
            install_tlog_from_bundle "$c"
            HAS_TLOG=$(sudo docker exec "$c" sh -c "command -v tlog-rec-session" 2>/dev/null)
            if [ -z "$HAS_TLOG" ]; then
                echo "[$c] INSTALL FAILED — skipping shell flip"
                continue
            else
                echo "[$c] install succeeded"
            fi
        fi
    fi

    CURRENT_SHELL=$(sudo docker exec "$c" sh -c "grep '^root:' /etc/passwd | cut -d: -f7")

    if [ "$CURRENT_SHELL" == "/usr/bin/tlog-rec-session" ]; then
        echo "[$c] ALREADY DONE"
        continue
    fi

    if [ "$MODE" == "check" ]; then
        echo "[$c] READY — current shell: $CURRENT_SHELL"
        continue
    fi

    if [ "$MODE" == "apply" ]; then
        echo "$c:$CURRENT_SHELL" >> "$LOGFILE"
        sudo docker exec "$c" mkdir -p /var/log/tlog /var/run/tlog
        sudo docker exec "$c" sh -c "grep -qxF '/usr/bin/tlog-rec-session' /etc/shells || echo '/usr/bin/tlog-rec-session' >> /etc/shells"
        sudo docker exec "$c" sed -i -e 's|// "shell" : "/bin/bash",|"shell" : "/bin/bash",|' -e 's|// "path" : ""|"path" : "/var/log/tlog/session.log"|' -e 's|// "writer" : "syslog"|"writer" : "syslog"|' /etc/tlog/tlog-rec-session.conf
        sudo docker exec "$c" sh -c "awk -F: 'BEGIN{OFS=\":\"} \$1==\"root\"{\$7=\"/usr/bin/tlog-rec-session\"} {print}' /etc/passwd > /etc/passwd.tmp && mv /etc/passwd.tmp /etc/passwd"

        NEW_SHELL=$(sudo docker exec "$c" sh -c "grep '^root:' /etc/passwd | cut -d: -f7")
        if [ "$NEW_SHELL" == "/usr/bin/tlog-rec-session" ]; then
            echo "[$c] APPLIED"
        else
            echo "[$c] FAILED — shell still: $NEW_SHELL"
        fi
    fi
done

if [ "$MODE" == "rollback" ]; then
    if [ ! -f "$LOGFILE" ]; then
        echo "No rollback log found."
        exit 0
    fi
    while IFS=: read -r c orig_shell; do
        sudo docker exec "$c" sh -c "awk -F: -v orig=\"$orig_shell\" 'BEGIN{OFS=\":\"} \$1==\"root\"{\$7=orig} {print}' /etc/passwd > /etc/passwd.tmp && mv /etc/passwd.tmp /etc/passwd"
        echo "[$c] rolled back to $orig_shell"
    done < "$LOGFILE"
    rm -f "$LOGFILE"
fi
