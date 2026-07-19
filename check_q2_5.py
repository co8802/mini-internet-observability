import sys                     # reads the group number typed on the command line
import subprocess               # lets us run shell commands, like ssh, from python
import re                        # used to search and pull patterns out of live command output

# this script checks q2.5, using as-path prepending to make one link look
# less attractive to other ases, using only live, real time network
# state, not saved config
#
# fixed from an earlier version that also checked for prohibited deny
# rules by reading route maps directly out of saved config. that check
# went through three real rounds of fixing to correctly exclude
# legitimate rpki denies, trailing catch-alls, and ixp same-region
# denies, but its still fundamentally a static config check underneath
# all that, exactly the category thats already handled elsewhere. this
# version keeps only the one real live check: whether prepending
# actually shows up on the router's real, live advertised routes right
# now, not whether a rule for it exists somewhere in the config
#
# still not covered, and why: whether the prepending is on the actual
# high delay link, we dont know which link that is for each group, real
# traceroute measurement done separately tonight found a strong
# candidate but that was done by hand, not automated, since judging
# "is this delay unusually high" needs human judgment, not a fixed rule.
# also whether incoming traffic is being optimized, the spec asks for
# both directions and this only checks outgoing prepending

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
    # we still need the config to figure out which peers exist at all,
    # this is just used for discovery, not for checking correctness
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"   # confirmed pattern from goto.sh
    proxy_port = str(2000 + group)   # every group's proxy sits on port 2000+groupnum
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
        # if ssh fails for any reason, just return nothing instead of crashing
        return None


def get_bgp_neighbors(config_text, own_asn):
    # only care about ebgp neighbors, prepending is about what we send
    # to other ases, not our own routers
    remote_as_lines = re.findall(r'neighbor (\S+) remote-as (\S+)', config_text)
    ebgp_peers = [ip for ip, peer_asn in remote_as_lines if peer_asn != str(own_asn)]
    return ebgp_peers


def get_advertised_routes(group, router_id, peer_ip):
    # the real, live check, asks the router right now what its actually
    # advertising to a specific neighbor, this is where we look for real
    # prepending in the as-path column
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


def has_advertised_prefix(advertised_output):
    # checks for a real ip prefix pattern, this is a much more reliable
    # signal that actual routes exist than just checking if the output
    # is nonempty, since ssh output always includes the frr login banner
    # text regardless of whether there are any real routes underneath it
    return bool(re.search(r'\d+\.\d+\.\d+\.\d+/\d+', advertised_output))


def check_prepending(advertised_output, own_asn):
    # real prepending looks like our own asn repeated 3+ times in a row
    # in the as-path, something like "3 3 3" instead of just "3"
    pattern = r'\b' + re.escape(str(own_asn)) + r'(\s+' + re.escape(str(own_asn)) + r'){2,}\b'
    return bool(re.search(pattern, advertised_output))


def check_q2_5(asn):
    found_any_prepending = False
    checked_any_session = False   # tracks whether we ever had real routes to look at at all

    print("=" * 50)
    print("Q2.5 Performance Optimization Check (live state) - AS " + str(asn))
    print("=" * 50)
    print("\nnote: this checks whether as-path prepending actually shows up")
    print("on live advertised routes right now, not whether a rule for it")
    print("exists in saved config. still cant confirm its on the actual")
    print("high delay link, that needs real measurement, done separately\n")

    for router_name, router_id in ROUTERS.items():
        config = get_router_config(asn, router_id)
        if config is None or "router bgp" not in config:
            continue   # skip routers we couldnt reach or that have no bgp at all

        peers = get_bgp_neighbors(config, asn)
        if not peers:
            continue   # this router has no outside connections, nothing to check

        print("[" + router_name + "]")

        for peer_ip in peers:
            advertised = get_advertised_routes(asn, router_id, peer_ip)

            # check for a real prefix first, since the raw ssh output
            # always includes the login banner even with zero real
            # routes, so checking for total emptiness would never
            # actually catch the genuine "no routes yet" case
            if not advertised or not has_advertised_prefix(advertised):
                print("  " + peer_ip + ": no advertised routes to check right now")
                continue

            checked_any_session = True
            has_prepend = check_prepending(advertised, asn)
            if has_prepend:
                print("  " + peer_ip + ": as-path prepending found")
                found_any_prepending = True
            else:
                print("  " + peer_ip + ": no prepending found on this advertisement")

    # print the final tally and wrap up
    print("\n" + "=" * 50)
    if not checked_any_session:
        print("No advertised routes were available to check for this group right now.")
    elif found_any_prepending:
        print("Found at least one advertisement using as-path prepending.")
        print("Still need to confirm this is on the actual high delay link.")
    else:
        print("No as-path prepending found anywhere for this group.")
    print("=" * 50)


if __name__ == "__main__":
    # default to group 3 if no group number given
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_5(asn)
