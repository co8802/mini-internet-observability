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
    except Exception:
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


def parse_route_map_entries(config_text, route_map_name):
    entries = re.findall(
        r'route-map ' + re.escape(route_map_name) + r' (permit|deny) (\d+)\n(.*?)(?=\nroute-map |\n!|\Z)',
        config_text, re.DOTALL
    )
    return sorted(entries, key=lambda e: int(e[1]))


def has_real_filtering(entries):
    for action, seq, body in entries:
        if 'match' in body:
            return True
    return False


def find_own_prefix_lists(config_text, own_asn):
    own_net = str(own_asn) + '.0.0.0/8'
    matches = re.findall(r'ip prefix-list (\S+) seq \d+ permit ' + re.escape(own_net), config_text)
    return set(matches)


def find_origin_community(config_text, own_prefix_list_names):
    for pl_name in own_prefix_list_names:
        pattern = r'route-map \S+ permit \d+\n(?:.*\n)*?\s*match ip address prefix-list ' + re.escape(pl_name) + r'\n(?:.*\n)*?\s*set community (\S+)'
        match = re.search(pattern, config_text)
        if match:
            return match.group(1)
    return None


def find_community_lists_containing(config_text, community_value):
    lists = re.findall(r'bgp community-list (\d+) seq \d+ permit (\S+)', config_text)
    matching_numbers = set()
    for list_num, comm_val in lists:
        if comm_val == community_value:
            matching_numbers.add(list_num)
    return matching_numbers


def own_prefix_permitted(config_text, entries, own_asn):
    if not entries:
        return False

    own_prefix_lists = find_own_prefix_lists(config_text, own_asn)
    origin_community = find_origin_community(config_text, own_prefix_lists) if own_prefix_lists else None
    matching_community_lists = (
        find_community_lists_containing(config_text, origin_community)
        if origin_community else set()
    )

    own_prefix_seq = None
    for action, seq, body in entries:
        if action != 'permit':
            continue
        if any(pl in body for pl in own_prefix_lists):
            own_prefix_seq = int(seq)
            break
        matched_list_nums = re.findall(r'match community (\S+)', body)
        if any(num in matching_community_lists for num in matched_list_nums):
            own_prefix_seq = int(seq)
            break

    if own_prefix_seq is None:
        return False

    for action, seq, body in entries:
        if int(seq) >= own_prefix_seq:
            break
        if action == 'deny' and 'match' not in body:
            return False

    return True


def check_localpref_used(advertised_output):
    locprefs = re.findall(r'^\s*\*>?\s*\S+\s+\S+\s+\d*\s+(\d+)', advertised_output, re.MULTILINE)
    if not locprefs:
        return None
    return any(lp != '100' for lp in locprefs)


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

            out_entries = parse_route_map_entries(config, out_rmap) if out_exists else []

            if out_exists:
                real_filtering = has_real_filtering(out_entries)
                label_filter = label_base + " egress route map has real filtering logic (at least one match clause)"
                if real_filtering:
                    print("  PASS: " + label_filter)
                else:
                    print("  FAIL: " + label_filter + " (unconditional permit, no actual export policy)")
                check(label_filter, real_filtering)

            if out_exists:
                permitted = own_prefix_permitted(config, out_entries, asn)
                label_permit = label_base + " own prefix is genuinely permitted through egress"
                if permitted:
                    print("  PASS: " + label_permit)
                else:
                    print("  FAIL: " + label_permit)
                check(label_permit, permitted)

            advertised = get_advertised_routes(asn, router_id, peer_ip)
            if advertised:
                lp_used = check_localpref_used(advertised)
                if lp_used is None:
                    print("  INFO: " + label_base + " no routes advertised yet, cant check local-pref")
                else:
                    label_lp = label_base + " local-pref differs from FRR default (mechanism check only)"
                    if lp_used:
                        print("  PASS: " + label_lp)
                    else:
                        print("  FAIL: " + label_lp)
                    check(label_lp, lp_used)

    print("\n[Info] Still not verified, needs data we dont have yet:")
    print("  whether the local-pref ranking actually matches customer >")
    print("  peer > provider correctly for each specific session, and")
    print("  whether ixp sessions are specifically treated as peer-to-peer.")
    print("  both need per-session business relationship data from kostas")
    print("  or the connections page before they can be checked properly.")

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q2.3 check PASSED (relationship-specific ranking not verified)")
    else:
        print("Q2.3 check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_3(asn)
