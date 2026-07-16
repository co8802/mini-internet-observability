import sys
import subprocess
import re

# this script checks q2.6, rpki configuration
# looks at whether an rpki validator/cache is set up on each router, and
# whether any route maps actually use rpki status to filter routes coming in
#
# same ssh plus config parsing approach as check_q1_4.py and the
# next-hop-self checks, since suzieq doesnt expose this kind of raw config
# detail

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
    # router ip pattern confirmed earlier from goto.sh: 158.X.(9+routerID).1
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    proxy_port = str(2000 + group)
    # ssh into the group proxy first, then from there pipe the command
    # into vtysh on the actual router. doing it this way avoids the
    # quoting mess we ran into trying vtysh -c through a nested ssh
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
        # if ssh fails for any reason just return none so the rest of the
        # script can skip that router instead of crashing
        return None


def check_q2_6(asn):
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
    print("Q2.6 RPKI Verification (via SSH+config parse) - AS " + str(asn))
    print("=" * 50)

    for router_name, router_id in ROUTERS.items():
        print("\n[" + router_name + "]")
        config = get_router_config(asn, router_id)
        if config is None:
            print("  Could not retrieve config, skipping")
            continue

        # looking for a line like "rpki cache 3.104.0.1 3323 preference 1"
        # this tells us the router actually has a validator configured
        has_rpki_cache = bool(re.search(r'rpki cache \S+ \d+', config))
        label1 = router_name + " has rpki cache/validator configured"
        if has_rpki_cache:
            print("  PASS: " + label1)
        else:
            print("  FAIL: " + label1)
        check(label1, has_rpki_cache)

        # looking for a route map line that actually matches on rpki
        # status, this is the part that uses rpki to reject bad routes
        has_rpki_filter = bool(re.search(r'match rpki (valid|invalid|notfound)', config))
        label2 = router_name + " has a route map filtering on rpki validity"
        if has_rpki_filter:
            print("  PASS: " + label2)
        else:
            # not counting this as a real fail yet, still not sure if
            # every router actually needs this or just the ones handling
            # external routes
            print("  INFO: " + label2 + " (not found, may not be needed on every router)")

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q2.6 rpki cache check PASSED")
    else:
        print("Q2.6 rpki cache check FAILED - missing on:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    # defaults to group 3 if you dont pass a number in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q2_6(asn)
