import sys
import subprocess
import re

# this script checks q2.4, peering through the ixp using bgp communities
#
# same ssh plus config parsing approach as the other checks
#
# heads up, this is a mechanism check only, same deal as check_q2_5.py.
# it can tell us if community based filtering exists at all on the ixp
# session, but not whether its actually filtering the right ases. that
# would need us to know which ases are in the same region as this group,
# which we dont have yet. so this cant check the real outcome the
# question is asking for, just whether the ingredients are there
#
# note: a route map name in frr can have multiple numbered entries, like
# "route-map ex_141_OUT permit 10" and "route-map ex_141_OUT deny 20", both
# under the same name. the first version of this script only grabbed one
# block and missed the community line sitting in the other one. fixed by
# collecting every block with that name instead of stopping at the first

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


def find_ixp_sessions(config_text):
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    ixp_peers = [(ip, peer_asn) for ip, peer_asn in remote_as_lines if ip.startswith('180.')]
    return ixp_peers


def get_egress_route_map_name(config_text, peer_ip):
    match = re.search(r'neighbor ' + re.escape(peer_ip) + r' route-map (\S+) out', config_text)
    if match:
        return match.group(1)
    return None


def route_map_uses_community(config_text, route_map_name):
    blocks = re.findall(
        r'route-map ' + re.escape(route_map_name) + r' (?:permit|deny) \d+.*?exit',
        config_text, re.DOTALL
    )
    for block in blocks:
        if re.search(r'set community', block):
            return True
    return False


def check_q2_4(asn):
    passed = 0
    failed = 0
    fail_details = []
    found_ixp_session = False

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            fail_details.append(name)

    print("=" * 50)
    print("Q2.4 IXP Community Peering Check (via SSH, mechanism only) - AS " + str(asn))
    print("=" * 50)
    print("\nnote: this only checks if community based filtering exists on")
    print("the ixp session, not whether the right ases are actually being")
    print("filtered, since we dont know the region/zone layout yet\n")

    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            continue

        ixp_sessions = find_ixp_sessions(config)
        if not ixp_sessions:
            continue

        found_ixp_session = True
        print("[" + router_name + "]")
        for peer_ip, peer_asn in ixp_sessions:
            label_base = router_name + " -> IXP AS" + peer_asn + " (" + peer_ip + ")"

            rmap_name = get_egress_route_map_name(config, peer_ip)
            if rmap_name is None:
                print("  FAIL: " + label_base + " has no egress route map at all")
                check(label_base + " has an egress route map", False)
                continue

            uses_community = route_map_uses_community(config, rmap_name)
            label = label_base + " egress route map (" + rmap_name + ") uses communities"
            if uses_community:
                print("  PASS: " + label)
            else:
                print("  FAIL: " + label)
            check(label, uses_community)

    if not found_ixp_session:
        print("No IXP session found for this group, nothing to check here.")

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0 and found_ixp_session:
        print("Q2.4 mechanism check PASSED (outcome not verified, see note above)")
    elif found_ixp_session:
        print("Q2.4 mechanism check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_4(asn)
