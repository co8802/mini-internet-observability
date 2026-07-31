#!/bin/bash
# Creates a separate TA fallback account with real sudo/root access on every
# container. Does NOT touch root's own /etc/passwd entry at all.
# Genuinely self-contained: unpacks sudo from a bundled tarball (bundles/sudo_bundle.tar)
# on routers/hosts (no internet access); proxies install sudo via apk (genuine independent install).

MODE="${1:-check}"
BUNDLE="$HOME/mini-internet-observability/bundles/sudo_bundle.tar"
TA_PASSWORD="taminiint"   # TODO: replace with per-TA SSH keys before real use

TARGETS=$(sudo docker ps --format "{{.Names}}" | grep -E "(host[0-9]*$|router$|^[0-9]+_ssh$)")

install_sudo_from_bundle() {
    local c="$1"
    cat "$BUNDLE" | sudo docker exec -i "$c" tar -C / -xf -
}

for c in $TARGETS; do
    IS_PROXY=false
    [[ "$c" == *_ssh ]] && IS_PROXY=true

    HAS_SUDO=$(sudo docker exec "$c" sh -c "command -v sudo" 2>/dev/null)
    HAS_TA=$(sudo docker exec "$c" sh -c "grep '^ta:' /etc/passwd" 2>/dev/null)

    if [ "$MODE" == "check" ]; then
        if [ -z "$HAS_SUDO" ]; then
            echo "[$c] NEEDS sudo"
        elif [ -z "$HAS_TA" ]; then
            echo "[$c] has sudo, NEEDS ta account"
        else
            echo "[$c] ALREADY DONE"
        fi
        continue
    fi

    if [ "$MODE" == "apply" ]; then
        if [ -z "$HAS_SUDO" ]; then
            if [ "$IS_PROXY" = true ]; then
                echo "[$c] apk installing sudo..."
                sudo docker exec "$c" apk add --no-cache sudo
            else
                echo "[$c] installing sudo from bundle..."
                install_sudo_from_bundle "$c"
            fi
            HAS_SUDO=$(sudo docker exec "$c" sh -c "command -v sudo" 2>/dev/null)
            if [ -z "$HAS_SUDO" ]; then
                echo "[$c] INSTALL FAILED — skipping ta account creation"
                continue
            fi
        fi

        if [ -z "$HAS_TA" ]; then
            sudo docker exec "$c" adduser -D ta
            sudo docker exec "$c" sh -c "echo 'ta:${TA_PASSWORD}' | chpasswd"
            sudo docker exec "$c" sh -c "grep -qxF 'ta ALL=(ALL) ALL' /etc/sudoers || echo 'ta ALL=(ALL) ALL' >> /etc/sudoers"
        fi

        VERIFY=$(sudo docker exec "$c" sh -c "grep '^ta:' /etc/passwd")
        VERIFY_SUDO=$(sudo docker exec "$c" sh -c "grep 'ta ALL' /etc/sudoers")
        if [ -n "$VERIFY" ] && [ -n "$VERIFY_SUDO" ]; then
            echo "[$c] OK — ta account exists with sudo access"
        else
            echo "[$c] FAILED — ta:$VERIFY sudoers:$VERIFY_SUDO"
        fi
    fi
done
