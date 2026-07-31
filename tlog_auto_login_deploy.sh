#!/bin/bash
# enables automatic tlog recording at login on every proxy container.
# genuinely self-contained: unpacks from a bundled tarball (bundles/tlog_bundle.tar)
# rather than live-copying from any already-configured container

# where we'll keep a record of each container's original login shell,
# so we can undo this later if we ever need to
LOGFILE=~/tlog_deploy_rollback.log

# what mode to run in - "check" just looks and reports, "apply" makes real changes,
# "rollback" undoes everything. defaults to "check" if nothing is specified
MODE="${1:-check}"

# path to the pre-built tlog bundle - what actually gets unpacked onto each proxy
BUNDLE="$HOME/mini-internet-observability/bundles/tlog_bundle.tar"

# get every proxy container's name (anything matching a number followed by "_ssh")
TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "^[0-9]+_ssh$")

# reusable steps for installing tlog from the bundle onto one container
install_tlog_from_bundle() {
    local c="$1"  # the container's name, passed in when this function is called
    # read the bundle file and feed it straight into a tar-extract command
    # running inside the target container - this places every file from the
    # bundle onto that container's real filesystem
    cat "$BUNDLE" | sudo docker exec -i "$c" tar -C / -xf -
    # tlog needs this specific file to exist with the right ownership before
    # it can start recording - create it, set who owns it, set its permissions
    sudo docker exec "$c" sh -c "touch /var/run/utmp && chown root:utmp /var/run/utmp && chmod 664 /var/run/utmp"
}

# main loop - do everything below once for every proxy container
for c in $TARGETS; do
    # check whether tlog is already installed on this container
    HAS_TLOG=$(sudo docker exec "$c" sh -c "command -v tlog-rec-session" 2>/dev/null)

    if [ -z "$HAS_TLOG" ]; then
        # tlog isn't installed yet
        if [ "$MODE" == "check" ]; then
            # just report it and move to the next container, don't change anything
            echo "[$c] NEEDS INSTALL"
            continue
        fi
        if [ "$MODE" == "apply" ]; then
            # actually install it
            echo "[$c] Installing tlog from bundle..."
            install_tlog_from_bundle "$c"

            # check again now that we just tried installing it
            HAS_TLOG=$(sudo docker exec "$c" sh -c "command -v tlog-rec-session" 2>/dev/null)
            if [ -z "$HAS_TLOG" ]; then
                # still missing - the install didn't actually work
                echo "[$c] INSTALL FAILED — skipping shell flip"
                continue
            else
                echo "[$c] install succeeded"
            fi
        fi
    fi

    # check what this container's root account is currently set up to run at login
    # (the 7th field in /etc/passwd is always the login shell)
    CURRENT_SHELL=$(sudo docker exec "$c" sh -c "grep '^root:' /etc/passwd | cut -d: -f7")

    if [ "$CURRENT_SHELL" == "/usr/bin/tlog-rec-session" ]; then
        # it's already set to launch tlog at login - nothing left to do here
        echo "[$c] ALREADY DONE"
        continue
    fi

    if [ "$MODE" == "check" ]; then
        # just report what the current shell is, don't touch anything
        echo "[$c] READY — current shell: $CURRENT_SHELL"
        continue
    fi

    if [ "$MODE" == "apply" ]; then
        # save this container's original shell to our rollback log before we touch it,
        # in the format "container_name:original_shell"
        echo "$c:$CURRENT_SHELL" >> "$LOGFILE"

        # create the folders tlog needs to store its recordings and lock files
        sudo docker exec "$c" mkdir -p /var/log/tlog /var/run/tlog

        # add tlog-rec-session to the list of "allowed" login shells,
        # but only if it isn't already listed there
        sudo docker exec "$c" sh -c "grep -qxF '/usr/bin/tlog-rec-session' /etc/shells || echo '/usr/bin/tlog-rec-session' >> /etc/shells"

        # fill in tlog's config file with real values: which shell to hand off to
        # after recording starts, where to save the recording, and to send
        # recordings through syslog rather than a plain local file
        sudo docker exec "$c" sed -i -e 's|// "shell" : "/bin/bash",|"shell" : "/bin/bash",|' -e 's|// "path" : ""|"path" : "/var/log/tlog/session.log"|' -e 's|// "writer" : "syslog"|"writer" : "syslog"|' /etc/tlog/tlog-rec-session.conf

        # the actual step that makes recording automatic: rewrite /etc/passwd so that
        # root's login shell is now tlog-rec-session instead of a normal shell.
        # this reads every line, and for the one starting with "root", replaces
        # its 7th field (the shell) with our new value, then saves the result
        sudo docker exec "$c" sh -c "awk -F: 'BEGIN{OFS=\":\"} \$1==\"root\"{\$7=\"/usr/bin/tlog-rec-session\"} {print}' /etc/passwd > /etc/passwd.tmp && mv /etc/passwd.tmp /etc/passwd"

        # check the shell again to confirm the change actually took effect
        NEW_SHELL=$(sudo docker exec "$c" sh -c "grep '^root:' /etc/passwd | cut -d: -f7")
        if [ "$NEW_SHELL" == "/usr/bin/tlog-rec-session" ]; then
            echo "[$c] APPLIED"
        else
            # something didn't stick - report exactly what the shell is now instead
            echo "[$c] FAILED — shell still: $NEW_SHELL"
        fi
    fi
done

# rollback mode - undo everything, using the log file we built up along the way
if [ "$MODE" == "rollback" ]; then
    if [ ! -f "$LOGFILE" ]; then
        # nothing to roll back if the log doesn't even exist
        echo "No rollback log found."
        exit 0
    fi
    # read the log one line at a time, splitting each line at the colon into
    # a container name and its original shell
    while IFS=: read -r c orig_shell; do
        # same kind of rewrite as before, but this time putting the ORIGINAL
        # shell back instead of tlog's
        sudo docker exec "$c" sh -c "awk -F: -v orig=\"$orig_shell\" 'BEGIN{OFS=\":\"} \$1==\"root\"{\$7=orig} {print}' /etc/passwd > /etc/passwd.tmp && mv /etc/passwd.tmp /etc/passwd"
        echo "[$c] rolled back to $orig_shell"
    done < "$LOGFILE"
    # delete the rollback log now that everything's been restored
    rm -f "$LOGFILE"
fi
