import sys
import subprocess
import re

# this script checks next-hop-self on eBGP sessions specifically, per
# q2.2's tip: "you will have to use the next-hop-self command when you
# configure the external BGP sessions"
#
# same ssh+config-parse approach as check_q2_1_nexthop.py, since suzieq's
# nhSelf column is confirmed broken. this version filters to eBGP peers
# (remote-as different from our own asn) instead of iBGP peers

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


def check_next_hop_self_ebgp(config_text, own_asn):
    # keep only neighbor lines where remote-as does NOT match our own asn,
    # those are the ebgp sessions
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    ebgp_peers = [(ip, peer_asn) for ip, peer_asn in remote_as_lines if peer_asn != str(own_asn)]

    nhs_ips = set(re.findall(r'neighbor (\S+) next-hop-self', config_text))

    results = []
    for peer_ip, peer_asn in ebgp_peers:
        has_nhs = peer_ip in nhs_ips
        results.append((peer_ip, peer_asn, has_nhs))
    return results


def check_q2_2_nexthop(asn):
    passed = 0
    failed = 0
    fail_details = []

    print("=" * 50)
    print("eBGP Next-Hop-Self Verification (via SSH+config parse) - AS " + str(asn))
    print("=" * 50)

    for router_name, router_id in ROUTERS.items():
        print("\n[" + router_name + "]")
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            print("  Could not retrieve config or no BGP config found, skipping")
            continue

        results = check_next_hop_self_ebgp(config, asn)
        if not results:
            print("  No eBGP neighbors on this router")
            continue

        for peer_ip, peer_asn, has_nhs in results:
            label = router_name + " -> " + peer_ip + " (eBGP, AS" + peer_asn + ")"
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
        print("eBGP next-hop-self check PASSED")
    else:
        print("eBGP next-hop-self check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_2_nexthop(asn)
