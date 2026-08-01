#!/bin/bash
# detects and repairs broken host<->router veth links using the mini-internet's
# own connect_one_l3_host_router helper, rather than relying on docker networking

# this script needs to run from the mini-internet's own platform folder,
# since it borrows real setup code that expects to be run from there
cd ~/mini-internet/platform

# pull in the mini-internet's own helper files - these give us access to
# real variables and functions already used elsewhere in this project,
# instead of us having to guess or rebuild that logic ourselves
source config/subnet_config.sh
source setup/_parallel_helper.sh
source groups/docker_pid.map
source setup/_connect_utils.sh

# _connect_utils.sh turns on some very strict shell behavior that would
# cause our own script to quit unexpectedly the moment any single check
# fails (like checking a link that's supposed to be broken). turn that
# strictness back off so our script can keep running and actually report
# what it finds
set +o errexit; set +o nounset; set +o pipefail

# read the list of every group/as in the mini-internet into an array
readarray ASConfig < config/AS_config.txt
GroupNumber=${#ASConfig[@]}

# what mode to run in - "check" just looks and reports, "repair" fixes what it finds
MODE="${1:-check}"

# outer loop - go through every group one at a time
for ((k = 0; k < GroupNumber; k++)); do
    # split this group's config line into its individual pieces
    GroupK=(${ASConfig[$k]})
    GroupAS="${GroupK[0]}"
    GroupType="${GroupK[1]}"
    GroupRouterConfig="${GroupK[3]}"

    # ixp groups don't have host-router links the way normal groups do, so skip them
    if [ "${GroupType}" == "IXP" ]; then
        continue
    fi

    # read this group's list of routers/locations into an array
    readarray Routers < config/$GroupRouterConfig
    RouterNumber=${#Routers[@]}

    # inner loop - go through every router/location within this group
    for ((i = 0; i < RouterNumber; i++)); do
        RouterI=(${Routers[$i]})
        RouterRegion="${RouterI[0]}"
        HostImage="${RouterI[2]}"

        # skip locations that don't actually have a separate host container
        [ "$HostImage" == "N/A" ] && continue

        # build the real container names for this host and its router
        HostCtn="${GroupAS}_${RouterRegion}host"
        RouterCtn="${GroupAS}_${RouterRegion}router"

        # skip if either container genuinely doesn't exist (e.g. groups set up
        # a bit differently, with numbered hosts instead of one named host)
        sudo docker inspect "$HostCtn" > /dev/null 2>&1 || continue
        sudo docker inspect "$RouterCtn" > /dev/null 2>&1 || continue
        # check whether this host-router link's interface actually exists right now
        HAS_LINK=$(sudo docker exec "$HostCtn" sh -c "ip link show ${RouterRegion}router" 2>/dev/null || true)

        if [ -z "$HAS_LINK" ]; then
            # the interface is missing entirely - this link is genuinely broken
            echo "[$HostCtn <-> $RouterCtn] BROKEN — link missing"

            if [ "$MODE" == "repair" ]; then
                # rebuild the connection using the mini-internet's own real
                # connection-building code, so it's created exactly the same
                # correct way it would have been originally
                sudo bash -c "
                    source config/subnet_config.sh
                    source setup/_connect_utils.sh
                    connect_one_l3_host_router '${GroupAS}' '${RouterRegion}' ''
                "
                echo "  -> repaired"
            fi
        else
            # the interface exists - this link is healthy, nothing to do
            echo "[$HostCtn <-> $RouterCtn] OK"
        fi
    done
done
