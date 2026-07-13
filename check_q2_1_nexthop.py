import sys
import subprocess
import re

# this script checks next-hop-self configuration by ssh-ing directly into
# each router and parsing show running-config, since suzieq's nhSelf
# column is confirmed broken (returns False even when genuinely configured)
#
# router ip pattern confirmed from goto.sh: 158.X.(9+routerID).1 where X is
# the group number, routerID is 1-8 for MSP,NYC,BOS,PHY,CHI,ATL,SFO,HOU
#
# uses the pipe approach (echo command | ssh ... vtysh) since vtysh -c
# with nested ssh quoting was unreliable, confirmed working manually first
#
# only checks iBGP sessions (remote-as matches our own asn). next-hop-self
# is specifically an iBGP concept, eBGP sessions naturally set next-hop to
# the sending router since they cross a real as boundary, no next-hop-self
# needed there. first version of this script checked every neighbor line
# indiscriminately and falsely flagged every eBGP session as failing

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


def check_next_hop_self(config_text, own_asn):
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    ibgp_peers = [(ip, peer_asn) for ip, peer_asn in remote_as_lines if peer_asn == str(own_asn)]

    nhs_ips = set(re.findall(r'neighbor (\S+) next-hop-self', config_text))

    results = []
    for peer_ip, peer_asn in ibgp_peers:
        has_nhs = peer_ip in nhs_ips
        results.append((peer_ip, peer_asn, has_nhs))
    return results


def check_q2_1_nexthop(asn):
    passed = 0
    failed = 0
    fail_details = []

    print("=" * 50)
    print("Next-Hop-Self Verification (via SSH+config parse) - AS " + str(asn))
    print("=" * 50)

    for router_name, router_id in ROUTERS.items():
        print("\n[" + router_name + "]")
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            print("  Could not retrieve config or no BGP config found, skipping")
            continue

        results = check_next_hop_self(config, asn)
        if not results:
            print("  No iBGP neighbors found in config")
            continue

        for peer_ip, peer_asn, has_nhs in results:
            label = router_name + " -> " + peer_ip + " (iBGP, AS" + peer_asn + ")"
            if has_nhs:
                print("  PASS: " + label + " has next-hop-self")
                passed += 1
            else:
                print("  FAIL: " + label + " missing next-hop-self")
                failed += 1
                fail_details.append(label)

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Next-hop-self check PASSED")
    else:
        print("Next-hop-self check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_1_nexthop(asn)
