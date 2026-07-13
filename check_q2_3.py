import sys
import subprocess
import re

# this script checks q2.3, local-pref and business relationship policies
#
# rewritten to stop using suzieq's ingressRmap/egressRmap columns, since we
# found direct proof those are unreliable. suzieq said group 3's ixp
# session had no egress route map at all, but a direct ssh+grep on the
# real router config showed a real route map that was genuinely applied
# and genuinely uses communities. same category of problem as the
# confirmed broken nhSelf column. so this version reads the actual config
# straight off each router instead of trusting suzieq for this
#
# checks route map presence (ingress and egress) on every external ebgp
# session, same tier as before, still cannot verify actual local-pref
# values or whether the business relationship ranking (customer > peer >
# provider) is correct, that would need per-session relationship data we
# dont have yet plus parsing show ip bgp neighbor advertised-routes for
# the real localpref numbers

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


def get_external_neighbors(config_text, own_asn):
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    return [(ip, peer_asn) for ip, peer_asn in remote_as_lines if peer_asn != str(own_asn)]


def get_route_map_name(config_text, peer_ip, direction):
    match = re.search(r'neighbor ' + re.escape(peer_ip) + r' route-map (\S+) ' + direction, config_text)
    if match:
        return match.group(1)
    return None


def route_map_exists(config_text, route_map_name):
    return bool(re.search(r'route-map ' + re.escape(route_map_name) + r' (?:permit|deny) \d+', config_text))


def check_q2_3(asn):
    passed = 0
    failed = 0
    fail_details = []

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            fail_details.append(name)

    print("=" * 50)
    print("Q2.3 Local-Pref and Business Relationships (via SSH+config parse) - AS " + str(asn))
    print("=" * 50)

    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            continue

        externals = get_external_neighbors(config, asn)
        if not externals:
            continue

        print("\n[" + router_name + "]")
        for peer_ip, peer_asn in externals:
            label_base = router_name + " -> AS" + peer_asn + " (" + peer_ip + ")"

            in_rmap = get_route_map_name(config, peer_ip, "in")
            in_exists = route_map_exists(config, in_rmap) if in_rmap else False
            label_in = label_base + " has an ingress route map"
            if in_exists:
                print("  PASS: " + label_in + " (" + str(in_rmap) + ")")
            else:
                print("  FAIL: " + label_in)
            check(label_in, in_exists)

            out_rmap = get_route_map_name(config, peer_ip, "out")
            out_exists = route_map_exists(config, out_rmap) if out_rmap else False
            label_out = label_base + " has an egress route map"
            if out_exists:
                print("  PASS: " + label_out + " (" + str(out_rmap) + ")")
            else:
                print("  FAIL: " + label_out)
            check(label_out, out_exists)

    print("\n[Info] Local-pref values still not verified:")
    print("  this checks route map presence only. verifying the actual")
    print("  local-pref numbers, and whether they correctly rank customer")
    print("  over peer over provider, still needs per-session business")
    print("  relationship data we dont have yet, plus parsing localpref")
    print("  out of show ip bgp neighbor advertised-routes per session.")

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q2.3 route map presence check PASSED (local-pref not verified)")
    else:
        print("Q2.3 route map presence check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_3(asn)
