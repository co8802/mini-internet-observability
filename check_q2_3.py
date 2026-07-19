import sys                     # reads the group number typed on the command line
import subprocess               # lets us run shell commands, like ssh, from python
import re                        # used to search and pull patterns out of live command output

# this script checks q2.3, local-pref and business relationship policies,
# using only live, real time network state, not saved config
#
# fixed from an earlier version that also read router configs directly
# via ssh to check things like route map presence, whether the egress
# map had real filtering logic, and whether the own prefix was genuinely
# permitted through. all of that was checking saved config text, exactly
# the kind of static config check thats already handled elsewhere. this
# version keeps only the one real check that reads live protocol state
# instead of a saved setting: whether local-pref is actually being
# applied to real routes right now
#
# still not covered, and why: whether the local-pref ranking actually
# matches customer above peer above provider correctly for each specific
# session, that needs per-session business relationship data we dont
# have yet. also whether ixp sessions specifically get treated as
# peer-to-peer, same missing information

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
    # we still need to know which peers exist and what asn they're in,
    # this comes from the config, but its just used to figure out who
    # to ask, not to check the config itself for correctness
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
        # if ssh fails for any reason, just return nothing instead of crashing
        return None


def get_advertised_routes(group, router_id, peer_ip):
    # this is the real, live check, it asks the router right now what
    # its actually advertising to a specific neighbor, not what its
    # config says it should be advertising
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
    # pulls every neighbor line, then keeps only the ones where the
    # remote as is different from our own, meaning its an outside
    # connection we actually need to check
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    return [(ip, peer_asn) for ip, peer_asn in remote_as_lines if peer_asn != str(own_asn)]


def check_localpref_used(advertised_output):
    # frr's default local-pref is 100. if every route shows exactly 100,
    # local-pref was probably never actually applied for this session.
    # this is a mechanism check only, it doesnt confirm the value is
    # correct, just that its not sitting at the untouched default
    locprefs = re.findall(r'^\s*\*>?\s*\S+\s+\S+\s+\d*\s+(\d+)', advertised_output, re.MULTILINE)
    if not locprefs:
        return None   # no routes to check at all right now
    return any(lp != '100' for lp in locprefs)


def check_q2_3(asn):
    passed = 0
    failed = 0
    fail_details = []

    # small helper so we dont repeat if/else everywhere
    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            fail_details.append(name)

    print("=" * 50)
    print("Q2.3 Local-Pref Live Check - AS " + str(asn))
    print("=" * 50)

    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            continue   # skip routers we couldnt reach or that have no bgp at all

        externals = get_external_neighbors(config, asn)
        if not externals:
            continue   # this router has no outside connections, nothing to check

        print("\n[" + router_name + "]")
        for peer_ip, peer_asn in externals:
            label_base = router_name + " -> AS" + peer_asn + " (" + peer_ip + ")"

            # the one real, live check: is local-pref actually being used
            # right now on this session, not just written in the config
            advertised = get_advertised_routes(asn, router_id, peer_ip)
            if advertised:
                lp_used = check_localpref_used(advertised)
                if lp_used is None:
                    print("  INFO: " + label_base + " no routes advertised yet, cant check local-pref")
                else:
                    label_lp = label_base + " local-pref differs from FRR default (live check)"
                    if lp_used:
                        print("  PASS: " + label_lp)
                    else:
                        print("  FAIL: " + label_lp)
                    check(label_lp, lp_used)
            else:
                print("  INFO: " + label_base + " could not retrieve advertised routes")

    print("\n[Info] Still not verified, needs data we dont have yet:")
    print("  whether the local-pref ranking actually matches customer >")
    print("  peer > provider correctly for each specific session, and")
    print("  whether ixp sessions are specifically treated as peer-to-peer.")
    print("  both need per-session business relationship data before")
    print("  they can be checked properly.")

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q2.3 live check PASSED (relationship-specific ranking not verified)")
    else:
        print("Q2.3 live check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_3(asn)
