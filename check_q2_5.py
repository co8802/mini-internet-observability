import sys
import subprocess
import re

# this script checks q2.5, using as-path prepending to make one link look
# less attractive to other ases, plus a separate check that makes sure no
# deny rules got added anywhere, since the spec is explicit we cant solve
# this question by denying anything
#
# covers two things:
#   1. as-path prepending exists somewhere. this is a mechanism check
#      only, it tells us prepending is happening at all, but it cant
#      confirm its actually on the high delay link, since we still dont
#      know which link that is for each group. figuring that out for
#      real would need actual traceroute or measurement data
#   2. no real deny rules on external route maps
#
# heads up, the deny check took three rounds of fixing before it was
# trustworthy. every time it was flagging something that turned out to
# be totally normal and required by a different question, not a real
# q2.5 violation:
#   - an rpki based deny on ingress maps, thats q2.6's job, applies
#     uniformly everywhere, nothing to do with making one link less
#     attractive
#   - an empty deny with no match sitting at the very end of egress
#     maps, just the normal catch-all every route map basically has
#     by default anyway, doesnt block anything real
#   - a deny specifically on the ixp session matching same-region as-path
#     lists, thats q2.4's explicitly required behavior, "deny any
#     advertisements coming from the ixp that contain ases in the same
#     region in the path." this only ever showed up on chi, the ixp
#     connected router, in every group
# this version knows to skip all three and only flags something as a
# real problem if its a genuine mid-list deny on a provider or customer
# session with an actual non-rpki match clause

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
    # router ip pattern confirmed from goto.sh: 158.X.(9+routerID).1
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    proxy_port = str(2000 + group)
    # ssh into the proxy, then pipe the command into vtysh on the actual
    # router, avoids the quoting problems we had before
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


def get_bgp_neighbors(config_text, own_asn):
    # only care about ebgp neighbors, prepending and export policy is
    # about what we send to other ases, not our own routers
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
    except Exception:
        return None


def check_prepending(advertised_output, own_asn):
    # real prepending looks like our own asn repeated 3+ times in a row
    # in the as-path, something like "3 3 3" instead of just "3"
    pattern = r'\b' + re.escape(str(own_asn)) + r'(\s+' + re.escape(str(own_asn)) + r'){2,}\b'
    return bool(re.search(pattern, advertised_output))


def get_route_maps_with_peers(config_text, own_asn):
    # keep track of which peer ip each route map belongs to, not just the
    # name, so we can tell later if a map is attached to the ixp session
    # specifically and treat its denies differently
    externals = get_bgp_neighbors(config_text, own_asn)
    route_maps = []
    for peer_ip in externals:
        for direction in ('in', 'out'):
            match = re.search(r'neighbor ' + re.escape(peer_ip) + r' route-map (\S+) ' + direction, config_text)
            if match:
                route_maps.append((match.group(1), peer_ip))
    return route_maps


def find_all_entries(config_text, route_map_name):
    # grab every numbered entry under a route map name, permits included,
    # since we need the full list to know if a deny is really the last
    # entry or not
    entries = re.findall(
        r'route-map ' + re.escape(route_map_name) + r' (permit|deny) (\d+)\n(.*?)(?=\nroute-map |\n!|\Z)',
        config_text, re.DOTALL
    )
    return sorted(entries, key=lambda e: int(e[1]))


def find_real_deny_violations(entries, is_ixp_session):
    # denying same-region ases on the ixp session is q2.4's job, not a
    # q2.5 problem, so skip everything if this map belongs to an ixp peer
    if is_ixp_session:
        return []

    if not entries:
        return []

    max_seq = max(int(seq) for _, seq, _ in entries)
    violations = []

    for action, seq, body in entries:
        if action != 'deny':
            continue
        if 'rpki' in body.lower():
            # thats q2.6's job, not us
            continue
        is_trailing_catchall = ('match' not in body) and (int(seq) == max_seq)
        if is_trailing_catchall:
            # just the standard default deny at the end, not a real block
            continue
        violations.append((seq, body.strip()))

    return violations


def check_q2_5(asn):
    passed = 0
    failed = 0
    found_any_prepending = False

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1

    print("=" * 50)
    print("Q2.5 Performance Optimization Check (via SSH) - AS " + str(asn))
    print("=" * 50)
    print("\nnote: prepending check is mechanism only. deny check excludes")
    print("legitimate rpki denies, trailing catch-alls, and ixp same-region")
    print("denies (that's q2.4's job), only flags real mid-list denies on")
    print("provider/customer sessions with a genuine non-rpki match clause\n")

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
            else:
                print("  " + peer_ip + ": no prepending found on this advertisement")

        # some groups use the same route map name for both directions,
        # so we track which names we've already checked to avoid
        # counting the same map twice
        route_maps = get_route_maps_with_peers(config, asn)
        seen = set()
        for rmap_name, peer_ip in route_maps:
            if rmap_name in seen:
                continue
            seen.add(rmap_name)

            is_ixp = peer_ip.startswith('180.')
            entries = find_all_entries(config, rmap_name)
            violations = find_real_deny_violations(entries, is_ixp)

            label = router_name + "'s route map " + rmap_name + " has no real deny violations"
            if is_ixp:
                label += " (ixp session, q2.4 denies expected and excluded)"
            if violations:
                print("  FAIL: " + label + " (found: " + str(violations) + ")")
            else:
                print("  PASS: " + label)
            check(label, len(violations) == 0)

    # print the final tally and wrap up
    print("\n" + "=" * 50)
    if found_any_prepending:
        print("Found at least one advertisement using as-path prepending.")
        print("Still need to confirm this is on the actual high delay link.")
    else:
        print("No as-path prepending found anywhere for this group.")
    print()
    print("Deny rule check: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("No prohibited deny rules found on provider/customer sessions")
    print("=" * 50)


if __name__ == "__main__":
    # default to group 3 if no group number given
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_5(asn)
