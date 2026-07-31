#!/bin/bash
# Detects and repairs broken host<->router veth links using the mini-internet's
# own connect_one_l3_host_router helper, rather than relying on Docker networking.

cd ~/mini-internet/platform
source config/subnet_config.sh
source setup/_parallel_helper.sh
source groups/docker_pid.map
source setup/_connect_utils.sh
set +o errexit; set +o nounset; set +o pipefail
readarray ASConfig < config/AS_config.txt
GroupNumber=${#ASConfig[@]}

MODE="${1:-check}"

for ((k = 0; k < GroupNumber; k++)); do
    GroupK=(${ASConfig[$k]})
    GroupAS="${GroupK[0]}"
    GroupType="${GroupK[1]}"
    GroupRouterConfig="${GroupK[3]}"

    if [ "${GroupType}" == "IXP" ]; then
        continue
    fi

    readarray Routers < config/$GroupRouterConfig
    RouterNumber=${#Routers[@]}

    for ((i = 0; i < RouterNumber; i++)); do
        RouterI=(${Routers[$i]})
        RouterRegion="${RouterI[0]}"
        HostImage="${RouterI[2]}"

        [ "$HostImage" == "N/A" ] && continue

        HostCtn="${GroupAS}_${RouterRegion}host"
        RouterCtn="${GroupAS}_${RouterRegion}router"

        # Skip if containers don't exist (e.g. all-in-one groups with numbered hosts, handled separately)
        sudo docker inspect "$HostCtn" > /dev/null 2>&1 || continue
        sudo docker inspect "$RouterCtn" > /dev/null 2>&1 || continue

        HAS_LINK=$(sudo docker exec "$HostCtn" sh -c "ip link show ${RouterRegion}router" 2>/dev/null || true)

        if [ -z "$HAS_LINK" ]; then
            echo "[$HostCtn <-> $RouterCtn] BROKEN — link missing"
            if [ "$MODE" == "repair" ]; then
                sudo bash -c "
                    source config/subnet_config.sh
                    source setup/_connect_utils.sh
                    connect_one_l3_host_router '${GroupAS}' '${RouterRegion}' ''
                "
                echo "  -> repaired"
            fi
        else
            echo "[$HostCtn <-> $RouterCtn] OK"
        fi
    done
done
