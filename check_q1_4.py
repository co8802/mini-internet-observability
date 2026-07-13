import sys
import subprocess
import re

# this script checks q1.4, ipv6 addressing in dcn/dcs plus the 6in4 tunnel
# between atl and bos
#
# suzieq's interface table does not capture ipv6 addresses at all for this
# deployment (confirmed earlier: show interface brief on the router shows
# real ipv6 addresses that suzieq's interface data never reports), so this
# uses ssh directly into each router and parses the raw output instead

# only atl and bos matter for q1.4, atl is the dcs gateway, bos is the dcn
# gateway. the numbers are their router ids from the spec, used to build
# their fixed management ips
ROUTERS = {
    'ATL_router': 6,
    'BOS_router': 3,
}


def get_router_output(group, router_id, command):
    # router ip pattern confirmed from goto.sh: 158.X.(9+routerID).1
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    # proxy ssh port is always 2000 + group number
    proxy_port = str(2000 + group)

    # ssh into the group's proxy, then from there pipe our command into
    # vtysh on the actual router. the echo-pipe trick avoids the quoting
    # problems that came up trying to use vtysh -c through nested ssh
    cmd = (
        "ssh -p " + proxy_port +
        " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
        "\"echo '" + command + "' | ssh -o StrictHostKeyChecking=no root@" +
        router_ip + " vtysh\""
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as e:
        # if the ssh call fails for any reason, return None instead of
        # crashing so the rest of the script can handle a missing result
        return None


def get_router_bash_output(group, router_id, command):
    # same idea as get_router_output, but for plain linux commands instead
    # of frr commands. needed because the 6in4 tunnel is set up with raw
    # ip tunnel commands outside frr, so we need a normal shell, not vtysh
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    proxy_port = str(2000 + group)
    cmd = (
        "ssh -p " + proxy_port +
        " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
        "\"ssh -o StrictHostKeyChecking=no root@" + router_ip + " '" + command + "'\""
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as e:
        return None


def check_q1_4(asn):
    X = asn
    passed = 0
    failed = 0
    results = []

    # small helper so we dont repeat if/else everywhere
    def check(name, condition):
        nonlocal passed, failed
        if condition:
            results.append("  PASS: " + name)
            passed += 1
        else:
            results.append("  FAIL: " + name)
            failed += 1

    print("=" * 50)
    print("Q1.4 IPv6 + 6in4 Tunnel Verification (via SSH) - AS " + str(asn))
    print("=" * 50)

    # expected ipv6 prefixes per the spec, dcs uses x:200, dcn uses x:201
    dcs_prefix = str(X) + ":200"
    dcn_prefix = str(X) + ":201"

    print("\n[Check 1] ATL VLAN interfaces have IPv6 in DCS subnet:")
    atl_out = get_router_output(asn, ROUTERS['ATL_router'], 'show interface brief')
    if atl_out is None:
        check("Could not retrieve ATL interface data", False)
    else:
        # search the raw text for the interface name followed eventually
        # by the expected prefix. re.escape protects against special
        # characters in the prefix being read as regex syntax. re.DOTALL
        # lets the match span multiple lines, since the ipv6 address shows
        # up on a line below the interface name in the real output
        check("ATL-L2.10 has IPv6 in DCS block (" + dcs_prefix + "::/32)",
              bool(re.search(r'ATL-L2\.10.*?' + re.escape(dcs_prefix), atl_out, re.DOTALL)))
        check("ATL-L2.20 has IPv6 in DCS block (" + dcs_prefix + "::/32)",
              bool(re.search(r'ATL-L2\.20.*?' + re.escape(dcs_prefix), atl_out, re.DOTALL)))

    print("\n[Check 2] BOS VLAN interfaces have IPv6 in DCN subnet:")
    bos_out = get_router_output(asn, ROUTERS['BOS_router'], 'show interface brief')
    if bos_out is None:
        check("Could not retrieve BOS interface data", False)
    else:
        check("BOS-L2.10 has IPv6 in DCN block (" + dcn_prefix + "::/32)",
              bool(re.search(r'BOS-L2\.10.*?' + re.escape(dcn_prefix), bos_out, re.DOTALL)))
        check("BOS-L2.20 has IPv6 in DCN block (" + dcn_prefix + "::/32)",
              bool(re.search(r'BOS-L2\.20.*?' + re.escape(dcn_prefix), bos_out, re.DOTALL)))

    print("\n[Check 3] 6in4 tunnel exists on ATL and BOS:")
    # ip tunnel show lists tunnel interfaces at the linux level, bypassing
    # frr entirely since 6in4 tunnels are not frr constructs
    atl_tunnel = get_router_bash_output(asn, ROUTERS['ATL_router'], 'ip tunnel show')
    bos_tunnel = get_router_bash_output(asn, ROUTERS['BOS_router'], 'ip tunnel show')
    # printed raw so we can visually confirm what actually comes back,
    # left in deliberately since detecting a 6in4 tunnel this way was
    # unproven until tested against real data
    print("  ATL tunnel output: " + str(atl_tunnel))
    print("  BOS tunnel output: " + str(bos_tunnel))
    # .strip() removes whitespace so a blank-looking result doesn't
    # accidentally count as "a tunnel exists"
    check("ATL has a tunnel configured", bool(atl_tunnel and atl_tunnel.strip()))
    check("BOS has a tunnel configured", bool(bos_tunnel and bos_tunnel.strip()))

    # print the final tally and, if anything failed, list exactly what failed
    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q1.4 PASSED")
    else:
        print("Q1.4 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)


if __name__ == "__main__":
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_4(asn)
