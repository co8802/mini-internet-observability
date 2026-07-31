#!/bin/bash
# Creates a separate TA fallback account with real sudo/root access on every
# container. Does NOT touch root's own /etc/passwd entry at all.
# Genuinely self-contained: unpacks sudo from a bundled tarball (bundles/sudo_bundle.tar)
# on routers/hosts (no internet access); proxies install sudo via apk (genuine independent install).

# What mode to run in — "check" just looks and reports, "apply" actually makes changes.
# If nothing is typed after the script's name, default to "check" (the safe option).
MODE="${1:-check}"

# Path to the pre-built sudo bundle — this is what routers/hosts unpack from,
# since they have no internet access and can't just download sudo themselves.
BUNDLE="$HOME/mini-internet-observability/bundles/sudo_bundle.tar"

# The password every TA account gets for now. Flagged as temporary —
# a real deployment should use individual SSH keys instead of one shared password.
TA_PASSWORD="taminiint"   # TODO: replace with per-TA SSH keys before real use

# Build the list of every container we care about: anything ending in "host"
# (optionally followed by a number), ending in "router", or a number followed by "_ssh" (a proxy).
TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "(host[0-9]*$|router$|^[0-9]+_ssh$)")

# A reusable block of steps for installing sudo on a container that has no internet
# access — it just unpacks the pre-built bundle straight into that container's filesystem.
install_sudo_from_bundle() {
    local c="$1"  # the container's name, passed in when this function is called
    # Read the bundle file, and feed it directly into a tar-extract command running
    # inside the target container — this places every file from the bundle onto
    # that container's real filesystem, in the correct locations.
    cat "$BUNDLE" | sudo docker exec -i "$c" tar -C / -xf -
}

# Main loop — do everything below once for every container in our list.
for c in $TARGETS; do
    # Assume this container is NOT a proxy until we check otherwise.
    IS_PROXY=false
    # If the container's name ends in "_ssh", it IS a proxy — flip the flag.
    [[ "$c" == *_ssh ]] && IS_PROXY=true

    # Check if sudo is already installed on this container.
    # "command -v sudo" prints sudo's location if it exists, or nothing if it doesn't.
    HAS_SUDO=$(sudo docker exec "$c" sh -c "command -v sudo" 2>/dev/null)

    # Check if the "ta" account already exists, by looking for a line starting with "ta:"
    # in this container's /etc/passwd (the file listing all user accounts).
    HAS_TA=$(sudo docker exec "$c" sh -c "grep '^ta:' /etc/passwd" 2>/dev/null)

    # ---- CHECK MODE: just report what's needed, don't change anything ----
    if [ "$MODE" == "check" ]; then
        if [ -z "$HAS_SUDO" ]; then
            # HAS_SUDO is empty, meaning sudo isn't installed at all yet.
            echo "[$c] NEEDS sudo"
        elif [ -z "$HAS_TA" ]; then
            # Sudo exists, but the "ta" account itself doesn't yet.
            echo "[$c] has sudo, NEEDS ta account"
        else
            # Both sudo and the ta account already exist — nothing to do here.
            echo "[$c] ALREADY DONE"
        fi
        continue  # skip the rest of this loop, move on to the next container
    fi

    # ---- APPLY MODE: actually make the real changes ----
    if [ "$MODE" == "apply" ]; then
        # If sudo isn't installed yet, install it the right way for this container type.
        if [ -z "$HAS_SUDO" ]; then
            if [ "$IS_PROXY" = true ]; then
                # Proxies have real internet access, so a normal package install works.
                echo "[$c] apk installing sudo..."
                sudo docker exec "$c" apk add --no-cache sudo
            else
                # Routers/hosts have no internet access, so we unpack our pre-built bundle instead.
                echo "[$c] installing sudo from bundle..."
                install_sudo_from_bundle "$c"
            fi

            # Check again now that we just tried installing it, to see if it actually worked.
            HAS_SUDO=$(sudo docker exec "$c" sh -c "command -v sudo" 2>/dev/null)
            if [ -z "$HAS_SUDO" ]; then
                # Still missing after trying to install it — something went wrong.
                echo "[$c] INSTALL FAILED — skipping ta account creation"
                continue  # don't bother trying to create the account, move to the next container
            fi
        fi

        # If the "ta" account doesn't exist yet, create it and set it up.
        if [ -z "$HAS_TA" ]; then
            # Create a new, plain user account named "ta" ("-D" = use defaults, don't ask questions).
            sudo docker exec "$c" adduser -D ta
            # Set that account's password by piping "ta:<password>" into chpasswd.
            sudo docker exec "$c" sh -c "echo 'ta:${TA_PASSWORD}' | chpasswd"
            # Grant "ta" permission to use sudo, by adding a rule to /etc/sudoers —
            # but only if that exact rule isn't already there (avoids duplicate lines).
            sudo docker exec "$c" sh -c "grep -qxF 'ta ALL=(ALL) ALL' /etc/sudoers || echo 'ta ALL=(ALL) ALL' >> /etc/sudoers"
        fi

        # Final check: confirm the account really exists AND really has sudo permission,
        # by looking for both pieces of evidence directly on the container.
        VERIFY=$(sudo docker exec "$c" sh -c "grep '^ta:' /etc/passwd")
        VERIFY_SUDO=$(sudo docker exec "$c" sh -c "grep 'ta ALL' /etc/sudoers")

        # Only report success if BOTH checks found something — otherwise report exactly
        # what was and wasn't found, to help diagnose what went wrong.
        if [ -n "$VERIFY" ] && [ -n "$VERIFY_SUDO" ]; then
            echo "[$c] OK — ta account exists with sudo access"
        else
            echo "[$c] FAILED — ta:$VERIFY sudoers:$VERIFY_SUDO"
        fi
    fi
done
