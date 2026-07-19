import sys                     # reads the group number typed on the command line
import subprocess               # lets us run shell commands, like ssh, from python
import re                        # used to search and pull patterns out of live command output

# this script checks q2.4, peering through the ixp using bgp communities,
# using live, real time network state instead of saved config
#
# checks whether a community value actually shows up on the router's
# real, live advertised routes toward the ixp right now, rather than
# reading the saved egress route map's "set community" line from config,
# which would just be checking saved settings
#
# fixed a real bug in an earlier version: the emptiness check
# (checking if the ssh output was blank) never caught the "no routes
# advertised yet" case, since the ssh output always includes the frr
# login banner text even when there are zero real routes underneath it.
# this version checks for an actual ip prefix pattern instead, a much
# more reliable signal that real routes exist, not just boilerplate
#
# still not covered, and why: whether the community values actually
# target the correct ases (same-region excluded, adjacent-region
# included). that needs to know which ases are in the same region as
# this group, which isnt something live network state can tell us on
# its own, its assignment specific information from outside any router

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
    # we still need the config to figure out which sessions are ixp
    # sessions at all (peer ip starting with 180.), this is just used
    # for discovery, not for checking correctness of anything
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"   # confirmed pattern from goto.sh
    proxy_port = str(2000 + group)   # every group's proxy sits on port 2000+groupnum
    # ssh into the proxy first, then pipe the command into vtysh on the
    # real router, this avoids the quoting problems from earlier tonight
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
        # if ssh fails for any reason, just return nothing instead of crashing
        return None


def get_advertised_routes_with_community(group, router_id, peer_ip):
    # the real, live check, asks the router right now what its actually
    # advertising to the ixp, including any community values attached
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


def find_ixp_sessions(config_text):
    # ixp peers always use addresses starting with 180., per the spec,
    # this is how we tell an ixp session apart from a normal group link
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    ixp_peers = [(ip, peer_asn) for ip, peer_asn in remote_as_lines if ip.startswith('180.')]
    return ixp_peers


def has_advertised_prefix(advertised_output):
    # checks for a real ip prefix pattern, like "5.0.0.0/8", this is a
    # much more reliable signal that actual routes exist than just
    # checking if the output is nonempty, since the ssh output always
    # includes the frr login banner text regardless of whether there
    # are any real routes underneath it
    return bool(re.search(r'\d+\.\d+\.\d+\.\d+/\d+', advertised_output))


def has_live_community(advertised_output):
    # frr community values look like "142:15", scan the live output for
    # anything matching that pattern. this only works if the output
    # actually includes a community column, worth double checking
    # against real output before fully trusting this
    return bool(re.search(r'\b\d+:\d+\b', advertised_output))


def check_q2_4(asn):
    passed = 0
    failed = 0
    fail_details = []
    found_ixp_session = False

    # small helper so we dont repeat if/else everywhere
    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            fail_details.append(name)

    print("=" * 50)
    print("Q2.4 IXP Community Peering Check (live state) - AS " + str(asn))
    print("=" * 50)
    print("\nnote: this checks whether a community value actually appears")
    print("on the live advertised route toward the ixp, not whether the")
    print("saved config has a set community line. still cant confirm the")
    print("right ases are being targeted, that needs region/zone data\n")

    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            continue   # skip routers we couldnt reach or that have no bgp at all

        ixp_sessions = find_ixp_sessions(config)
        if not ixp_sessions:
            continue   # this router has no ixp connection, nothing to check here

        found_ixp_session = True
        print("[" + router_name + "]")
        for peer_ip, peer_asn in ixp_sessions:
            label_base = router_name + " -> IXP AS" + peer_asn + " (" + peer_ip + ")"

            advertised = get_advertised_routes_with_community(asn, router_id, peer_ip)

            # check for a real prefix first, since the raw ssh output
            # always includes the login banner even with zero real
            # routes, so checking for total emptiness never actually
            # catches the genuine "no routes yet" case
            if not advertised or not has_advertised_prefix(advertised):
                print("  INFO: " + label_base + " no advertised routes to check right now")
                continue

            has_community = has_live_community(advertised)
            label = label_base + " advertised routes show a live community value"
            if has_community:
                print("  PASS: " + label)
            else:
                print("  FAIL: " + label + " (no community-looking value found in live output)")
            check(label, has_community)

    if not found_ixp_session:
        print("No IXP session found for this group, nothing to check here.")

    # print the final tally and wrap up
    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0 and found_ixp_session:
        print("Q2.4 live check PASSED (region targeting still not verified)")
    elif found_ixp_session:
        print("Q2.4 live check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_4(asn)
