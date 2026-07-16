import sys
import subprocess
import re

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
    except Exception:
        return None


def get_external_neighbors(config_text, own_asn):
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    return [(ip, peer_asn) for ip, peer_asn in remote_as_lines if peer_asn != str(own_asn)]


def get_ingress_route_map_name(config_text, peer_ip):
    match = re.search(r'neighbor ' + re.escape(peer_ip) + r' route-map (\S+) in', config_text)
    if match:
        return match.group(1)
    return None


def get_local_pref_from_route_map(config_text, route_map_name):
    if not route_map_name:
        return None
    entries = re.findall(
        r'route-map ' + re.escape(route_map_name) + r' permit \d+\n(.*?)(?=\nroute-map |\n!|\Z)',
        config_text, re.DOTALL
    )
    values = []
    for entry in entries:
        match = re.search(r'set local-preference (\d+)', entry)
        if match:
            values.append(int(match.group(1)))
    if not values:
        return None
    return max(values)


def classify_relationship(peer_ip, peer_asn, own_asn):
    if peer_ip.startswith('180.'):
        return 'peer'
    if int(peer_asn) > own_asn:
        return 'customer'
    return 'provider'


def check_q2_3_localpref(asn):
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1

    print("=" * 50)
    print("Q2.3 Local-Pref Ranking Check (customer > peer > provider) - AS " + str(asn))
    print("=" * 50)

    by_relationship = {'customer': [], 'peer': [], 'provider': []}

    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            continue

        externals = get_external_neighbors(config, asn)
        for peer_ip, peer_asn in externals:
            relationship = classify_relationship(peer_ip, peer_asn, asn)
            in_rmap = get_ingress_route_map_name(config, peer_ip)
            local_pref = get_local_pref_from_route_map(config, in_rmap)

            label = router_name + " -> AS" + peer_asn + " (" + peer_ip + "), classified as " + relationship
            if local_pref is None:
                print("  INFO: " + label + ", no local-preference set found in ingress map")
            else:
                print("  " + label + ", local-preference = " + str(local_pref))
                by_relationship[relationship].append((router_name, peer_asn, local_pref))

    print("\n[Check] Local-pref ranking across relationship types:")

    customer_vals = [v for _, _, v in by_relationship['customer']]
    peer_vals = [v for _, _, v in by_relationship['peer']]
    provider_vals = [v for _, _, v in by_relationship['provider']]

    print("  customer local-prefs found: " + str(customer_vals))
    print("  peer local-prefs found: " + str(peer_vals))
    print("  provider local-prefs found: " + str(provider_vals))

    if customer_vals and provider_vals:
        customer_above_provider = min(customer_vals) > max(provider_vals)
        check("customer local-pref ranks above provider local-pref", customer_above_provider)
    else:
        print("  INFO: missing customer or provider local-pref data, cant compare")

    if customer_vals and peer_vals:
        customer_above_peer = min(customer_vals) > max(peer_vals)
        check("customer local-pref ranks above peer local-pref", customer_above_peer)
    else:
        print("  INFO: missing customer or peer local-pref data, cant compare")

    if peer_vals and provider_vals:
        peer_above_provider = min(peer_vals) > max(provider_vals)
        check("peer local-pref ranks above provider local-pref", peer_above_provider)
    else:
        print("  INFO: missing peer or provider local-pref data, cant compare")

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    print("=" * 50)


if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_3_localpref(asn)
