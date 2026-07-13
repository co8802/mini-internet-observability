import sys
import subprocess
import re

# this script checks q2.5, using as-path prepending to make one link look
# less attractive to other ases
#
# same ssh plus parsing approach as the other checks, since we need to see
# the actual as-path on advertised routes, and suzieq's asPathList column
# is confirmed empty for every route we have checked so far
#
# heads up, this is a mechanism check only right now, not a full q2.5
# check. it can tell us if prepending is happening anywhere at all, but
# not whether its happening on the actual high delay link, since we dont
# know yet which link is high delay for each group. that part still needs
# figuring out, maybe from the measurement service or by asking kostas

ROUTERS = {
    'MSP_router': 1,
    'NYC_router': 2,
    'BOS_router': 3,
    'PHY_router': 4,
    'CHI_router': 5,
    'ATL_router': 6,
    'SFO_router': 7,
    'HOU_router': 8,
}


def get_router_config(group, router_id):
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    proxy_port = str(2000 + group)
    cmd = (
        "ssh -p " + proxy_port +
        " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
        "\"echo 'show running-config' | ssh -o StrictHostKeyChecking=no root@" +
        router_ip + " vtysh\""
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as e:
        return None


def get_bgp_neighbors(config_text, own_asn):
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    ebgp_peers = [ip for ip, peer_asn in remote_as_lines if peer_asn != str(own_asn)]
    return ebgp_peers


def get_advertised_routes(group, router_id, peer_ip):
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    proxy_port = str(2000 + group)
    command = "show ip bgp neighbor " + peer_ip + " advertised-routes"
    cmd = (
        "ssh -p " + proxy_port +
        " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
        "\"echo '" + command + "' | ssh -o StrictHostKeyChecking=no root@" +
        router_ip + " vtysh\""
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as e:
        return None


def check_prepending(advertised_output, own_asn):
    pattern = r'\b' + re.escape(str(own_asn)) + r'(\s+' + re.escape(str(own_asn)) + r'){2,}\b'
    return bool(re.search(pattern, advertised_output))


def check_q2_5(asn):
    passed = 0
    failed = 0
    found_any_prepending = False

    print("=" * 50)
    print("Q2.5 AS-Path Prepending Check (via SSH, mechanism only) - AS " + str(asn))
    print("=" * 50)
    print("\nnote: this only checks if prepending exists anywhere, not")
    print("whether its on the specific high delay link, since we dont know")
    print("yet which link that is for this group\n")

    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            continue

        peers = get_bgp_neighbors(config, asn)
        if not peers:
            continue

        print("[" + router_name + "]")
        for peer_ip in peers:
            advertised = get_advertised_routes(asn, router_id, peer_ip)
            if advertised is None:
                print("  could not get advertised routes for " + peer_ip + ", skipping")
                continue

            has_prepend = check_prepending(advertised, asn)
            if has_prepend:
                print("  " + peer_ip + ": as-path prepending found")
                found_any_prepending = True
                passed += 1
            else:
                print("  " + peer_ip + ": no prepending found on this advertisement")

    print("\n" + "=" * 50)
    if found_any_prepending:
        print("Found at least one advertisement using as-path prepending.")
        print("Still need to confirm this is on the actual high delay link")
        print("before treating this as a real pass for q2.5.")
    else:
        print("No as-path prepending found anywhere for this group.")
        print("Could mean q2.5 isnt done yet, or could mean the group is")
        print("using a different approach, worth double checking manually.")
    print("=" * 50)


if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_5(asn)
