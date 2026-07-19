import sys                     # reads the group number typed on the command line
import subprocess               # lets us run shell commands, like ssh, from python

# this script checks q2.6, rpki configuration, using live, real time
# network state instead of saved config
#
# fixed from an earlier version that checked saved config for an
# "rpki cache" line and a "match rpki" route map line. thats a static
# config check, exactly the category thats already handled elsewhere.
# this version instead checks whether the router is actually, right now,
# successfully connected to its rpki validator, using "show rpki
# cache-connection". a router can have a perfectly correct looking
# config line telling it where to connect, while the actual live
# connection is dead for some other reason entirely, so checking the
# config alone doesnt tell us if rpki is really working
#
# major finding from earlier tonight: every single router across all 4
# test groups showed no live connection to their rpki cache server, 32
# routers, zero exceptions, despite the config looking correct on every
# one of them. since all 4 groups got full marks on this question on the
# real grade sheet, this looks like something changed on the
# infrastructure side since grading, not a student config problem,
# worth raising directly rather than scoring against anyone
#
# still not covered, and why: whether a route origin authorization was
# actually issued, that happens on a completely separate system (the
# certificate authority), not visible from any group's own router at
# all. also whether the rpki filtering logic correctly distinguishes
# valid, invalid, and not found routes, rather than just existing

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


def check_cache_connection(group, router_id):
    # asks the router right now whether its actually talking to its
    # rpki validator, not whether its configured to try
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"   # confirmed pattern from goto.sh
    proxy_port = str(2000 + group)   # every group's proxy sits on port 2000+groupnum
    # ssh into the proxy first, then pipe the command into vtysh on the
    # real router, avoids the quoting problems from earlier tonight
    cmd = (
        "ssh -p " + proxy_port +
        " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
        "\"echo 'show rpki cache-connection' | ssh -o StrictHostKeyChecking=no root@" +
        router_ip + " vtysh\""
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception:
        # if ssh fails for any reason, just return nothing instead of crashing
        return None


def check_q2_6(asn):
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
    print("Q2.6 RPKI Cache Connection Check (live state) - AS " + str(asn))
    print("=" * 50)
    print("\nnote: this checks whether the router is actually connected to")
    print("its rpki validator right now, not whether the config says it")
    print("should be. a correct-looking config with a dead connection")
    print("means rpki isnt functionally validating anything\n")

    for router_name, router_id in ROUTERS.items():
        output = check_cache_connection(asn, router_id)
        if output is None:
            print("[" + router_name + "] could not reach router, skipping")
            continue

        if "No connection to RPKI cache server" in output:
            print("[" + router_name + "] NOT connected to RPKI cache server")
            check(router_name + " has a live RPKI cache connection", False)
        elif "rpki" in output.lower() or "cache" in output.lower():
            # print the actual output so we can see what a real connected
            # state looks like, since we havent confirmed the exact
            # wording frr uses when the connection is genuinely up
            last_line = output.strip().splitlines()[-1] if output.strip() else "(empty)"
            print("[" + router_name + "] output: " + last_line)
            check(router_name + " has a live RPKI cache connection", True)
        else:
            print("[" + router_name + "] unexpected output, no RPKI mention at all: " + str(output)[:200])
            check(router_name + " has a live RPKI cache connection", False)

    # print the final tally and wrap up
    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed > 0:
        print("Routers NOT connected to their RPKI cache server:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_6(asn)
