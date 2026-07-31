#!/bin/bash
# Full recovery sequence to run after any VM reboot.
# Rebuilds the mini-internet topology, restores SuzieQ's SSH key access,
# and re-deploys tlog/rsyslog/ta to every container.
# Safe to re-run — every step is idempotent (checks before acting).

set -e

echo "=== Step 1: Rebuilding mini-internet topology ==="
cd ~/mini-internet/platform
sudo bash startup.sh

echo "=== Step 2: Restoring SuzieQ SSH key access on proxy containers ==="
SUZIEQ_KEY=$(cat ~/suzieq/keys/master/id_rsa.pub)
for g in 3 4 5 6; do
    echo "  -> group $g"
    ALREADY_PRESENT=$(sudo docker exec "${g}_ssh" sh -c "grep -qxF '$SUZIEQ_KEY' /root/.ssh/authorized_keys && echo yes" 2>/dev/null)
    if [ "$ALREADY_PRESENT" == "yes" ]; then
        echo "     already present, skipping"
    else
        sudo docker exec -i "${g}_ssh" bash -c "cat >> /root/.ssh/authorized_keys" < ~/suzieq/keys/master/id_rsa.pub
        echo "     key added"
    fi
done

echo "=== Step 3: Re-deploying tlog to all proxies ==="
~/tlog_auto_login_deploy.sh apply

echo "=== Step 4: Re-deploying rsyslog to all containers ==="
~/rsyslog_deploy.sh apply

echo "=== Step 5: Re-deploying TA fallback accounts to all containers ==="
~/ta_account_deploy.sh apply

echo "=== Recovery complete ==="
