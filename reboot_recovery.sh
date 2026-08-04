#!/bin/bash
# full recovery sequence to run after any vm reboot.
# rebuilds the mini-internet topology, restores suzieq's ssh key access,
# and re-deploys tlog/rsyslog/ta to every container.
# safe to re-run - every step is idempotent (checks before acting)

# stop the whole script immediately if any single command fails,
# rather than pushing on and potentially making things worse
set -e

echo "=== Step 1: Rebuilding mini-internet topology ==="
# this has to run from the mini-internet's own platform folder
cd ~/mini-internet/platform
# this is the mini-internet's own real startup script - rebuilds every
# container and every network connection from scratch
sudo bash startup.sh

echo "=== Step 2: Restoring SuzieQ SSH key access on proxy containers ==="
# read our saved public key into a variable, so we can check for it and add it
SUZIEQ_KEY=$(cat ~/suzieq/keys/master/id_rsa.pub)

# only groups 3-6 ever had this key manually added, so those are the only
# ones that need it restored
for g in 3 4 5 6; do
    echo "  -> group $g"

    # check if our key is already sitting in this proxy's list of allowed keys
    ALREADY_PRESENT=$(sudo docker exec "${g}_ssh" sh -c "grep -qxF '$SUZIEQ_KEY' /root/.ssh/authorized_keys && echo yes" 2>/dev/null)

    if [ "$ALREADY_PRESENT" == "yes" ]; then
        # already there - don't add it again, that would create a duplicate
        echo "     already present, skipping"
    else
        # not there yet - add it now
        sudo docker exec -i "${g}_ssh" bash -c "cat >> /root/.ssh/authorized_keys" < ~/suzieq/keys/master/id_rsa.pub
        echo "     key added"
    fi
done

echo "=== Step 3: Re-deploying tlog to all proxies ==="
# our tlog script already checks what's needed before doing anything,
# so it's safe to just run it again here
~/tlog_auto_login_deploy.sh apply

echo "=== Step 4: Re-deploying rsyslog to all containers ==="
# same idea - safe to re-run, it only changes what actually needs changing
~/rsyslog_deploy.sh apply

echo "=== Step 5: Re-deploying TA fallback accounts to all containers ==="
# same idea again - safe to re-run
~/ta_account_deploy.sh apply

echo "=== Step 6: Re-checking centralized connector on all proxies ==="
~/setup_centralized_connector.sh apply

echo "=== Recovery complete ==="
