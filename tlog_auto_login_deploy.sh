#!/bin/bash
# Loops over mini-internet containers and enables automatic tlog recording at login.
# Copies real file content via pipes (dereferences symlinks naturally) and
# explicitly recreates symlinks with known-correct targets, avoiding docker cp's
# unreliable symlink handling. Safe by design: only ever touches container files
# via docker exec, never depends on a container's own login shell.

LOGFILE=~/tlog_deploy_rollback.log
MODE="${1:-check}"
SOURCE="3_ssh"

TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "(host[0-9]*$|router$|^[0-9]+_ssh$)")
# Once confident, swap to:
# TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "(host[0-9]*$|router$|^[0-9]+_ssh$)")

install_tlog() {
    local c="$1"

    REALFILES="libbrotlicommon.so.1.1.0 libbrotlidec.so.1.1.0 libcurl.so.4.8.0 libidn2.so.0.3.8 libpsl.so.5.3.5 libtlog.so.0.0.0 libunistring.so.5.0.0 libcares.so.2.12.0"
    for f in $REALFILES; do
        sudo docker exec "$SOURCE" cat "/usr/lib/$f" | sudo docker exec -i "$c" sh -c "cat > /usr/lib/$f"
    done

    sudo docker exec "$c" sh -c '
        ln -sf libbrotlicommon.so.1.1.0 /usr/lib/libbrotlicommon.so.1
        ln -sf libbrotlicommon.so.1 /usr/lib/libbrotlicommon.so
        ln -sf libbrotlidec.so.1.1.0 /usr/lib/libbrotlidec.so.1
        ln -sf libbrotlidec.so.1 /usr/lib/libbrotlidec.so
        ln -sf libcurl.so.4.8.0 /usr/lib/libcurl.so.4
        ln -sf libcurl.so.4 /usr/lib/libcurl.so
        ln -sf libidn2.so.0.3.8 /usr/lib/libidn2.so.0
        ln -sf libidn2.so.0 /usr/lib/libidn2.so
        ln -sf libpsl.so.5.3.5 /usr/lib/libpsl.so.5
        ln -sf libpsl.so.5 /usr/lib/libpsl.so
        ln -sf libtlog.so.0.0.0 /usr/lib/libtlog.so.0
        ln -sf libtlog.so.0 /usr/lib/libtlog.so
        ln -sf libunistring.so.5.0.0 /usr/lib/libunistring.so.5
        ln -sf libcares.so.2.12.0 /usr/lib/libcares.so.2
        ln -sf libcares.so.2 /usr/lib/libcares.so
    '

    for f in tlog-rec tlog-rec-session tlog-play; do
        sudo docker exec "$SOURCE" cat "/usr/bin/$f" | sudo docker exec -i "$c" sh -c "cat > /usr/bin/$f && chmod +x /usr/bin/$f"
    done

    sudo docker exec "$c" mkdir -p /usr/share/tlog /etc/tlog

    for f in tlog-rec.default.conf tlog-rec-session.default.conf tlog-play.default.conf; do
        sudo docker exec "$SOURCE" cat "/usr/share/tlog/$f" | sudo docker exec -i "$c" sh -c "cat > /usr/share/tlog/$f"
    done

    for f in tlog-rec.conf tlog-rec-session.conf tlog-play.conf; do
        sudo docker exec "$SOURCE" cat "/etc/tlog/$f" | sudo docker exec -i "$c" sh -c "cat > /etc/tlog/$f"
    done

    # utmp fix, folded into install now
    sudo docker exec "$c" sh -c "touch /var/run/utmp && chown root:utmp /var/run/utmp && chmod 664 /var/run/utmp"
}

echo "Found $(echo "$TARGETS" | wc -w) candidate containers."
echo "---"

for c in $TARGETS; do
    HAS_TLOG=$(sudo docker exec "$c" sh -c "command -v tlog-rec-session" 2>/dev/null)

    if [ -z "$HAS_TLOG" ]; then
        if [ "$MODE" == "check" ]; then
            echo "[$c] NEEDS INSTALL — tlog not present yet"
            continue
        fi
        if [ "$MODE" == "apply" ]; then
            echo "[$c] Installing tlog from $SOURCE..."
            install_tlog "$c"
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
        sudo docker exec "$c" sed -i -e 's|// "shell" : "/bin/bash",|"shell" : "/bin/bash",|' -e 's|// "path" : ""|"path" : "/var/log/tlog/session.log"|' -e 's|// "writer" : "syslog"|"writer" : "file"|' /etc/tlog/tlog-rec-session.conf
        sudo docker exec "$c" sh -c "awk -F: 'BEGIN{OFS=\":\"} \$1==\"root\"{\$7=\"/usr/bin/tlog-rec-session\"} {print}' /etc/passwd > /etc/passwd.tmp && mv /etc/passwd.tmp /etc/passwd"

        NEW_SHELL=$(sudo docker exec "$c" sh -c "grep '^root:' /etc/passwd | cut -d: -f7")
        if [ "$NEW_SHELL" == "/usr/bin/tlog-rec-session" ]; then
            echo "[$c] APPLIED"
        else
            echo "[$c] FAILED to apply — shell still: $NEW_SHELL"
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
