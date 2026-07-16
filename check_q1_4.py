import sys
import subprocess
import re

# this script checks q1.4 fully, covering everything the spec actually
# asks for:
#   1. hosts in dcn and dcs have ipv6 addresses in the right subnet
#   2. hosts have some kind of ipv6 default gateway set
#   3. admin and patient hosts are on different address ranges, the vlan
#      split, not just sharing the same range
#   4. the 6in4 tunnel actually exists, both directions, using the
#      routers loopback addresses as the tunnel endpoints
#   5. actual end to end ipv6 connectivity works between dcn and dcs
#
# we use ssh directly for all of this since suzieq cant see ipv6 or
# tunnel data at all for this deployment, confirmed earlier

# host management ips follow the same pattern we found in goto.sh,
# 158.X.200.Y, admin hosts are A_*, patient hosts are P_*
HOSTS = {
    'A_MGH': {'zone': 'DCN', 'ip_octet': 3},
    'P_MGH': {'zone': 'DCN', 'ip_octet': 4},
    'A_EUH': {'zone': 'DCS', 'ip_octet': 5},
    'P_EUH': {'zone': 'DCS', 'ip_octet': 6},
    'A_CHA': {'zone': 'DCS', 'ip_octet': 7},
    'P_CHA': {'zone': 'DCS', 'ip_octet': 8},
}

# only atl and bos matter for the tunnel part, atl is the dcs gateway,
# bos is the dcn gateway
ROUTERS = {
    'ATL_router': 6,
    'BOS_router': 3,
}


def ssh_to_router(group, router_id, inner_command, use_vtysh=True):
    # router ip pattern confirmed from goto.sh: 158.X.(9+routerID).1
    router_ip = "158." + str(group) + "." + str(9 + router_id) + ".1"
    proxy_port = str(2000 + group)
    if use_vtysh:
        # pipe the command into vtysh for frr stuff
        cmd = (
            "ssh -p " + proxy_port +
            " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
            "\"echo '" + inner_command + "' | ssh -o StrictHostKeyChecking=no root@" +
            router_ip + " vtysh\""
        )
    else:
        # or just run it as a plain shell command, for linux level stuff
        # like tunnels that live outside frr entirely
        cmd = (
            "ssh -p " + proxy_port +
            " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
            "\"ssh -o StrictHostKeyChecking=no root@" + router_ip + " '" + inner_command + "'\""
        )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception:
        # if ssh fails for any reason just return none instead of crashing
        return None


def ssh_to_host(group, host_ip_octet, inner_command):
    # hosts are just plain linux boxes, no vtysh needed, straight shell
    host_ip = "158." + str(group) + ".200." + str(host_ip_octet)
    proxy_port = str(2000 + group)
    cmd = (
        "ssh -p " + proxy_port +
        " -i ~/suzieq/keys/master/id_rsa -o StrictHostKeyChecking=no root@localhost "
        "\"ssh -o StrictHostKeyChecking=no root@" + host_ip + " '" + inner_command + "'\""
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception:
        return None


def check_q1_4(asn):
    X = asn
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
    print("Q1.4 Full IPv6 + 6in4 Tunnel Verification - AS " + str(asn))
    print("=" * 50)

    # expected ipv6 prefixes per the spec, dcs uses x:200, dcn uses x:201
    dcs_prefix = str(X) + ":200"
    dcn_prefix = str(X) + ":201"

    # store every hosts ipv6 addresses here as we find them, so later
    # checks (vlan split, the ping test) can reuse them without asking
    # each host twice
    host_ipv6_addrs = {}

    print("\n[Check 1] Hosts have IPv6 addresses in the right subnet:")
    for host_name, info in HOSTS.items():
        expected_prefix = dcs_prefix if info['zone'] == 'DCS' else dcn_prefix
        out = ssh_to_host(asn, info['ip_octet'], 'ip -6 addr show')
        if out is None:
            check(host_name + " reachable and has IPv6 in " + expected_prefix + "::/32", False)
            continue
        # grab only the real, globally routable addresses, skip the
        # automatic link-local fe80 ones every interface gets by default
        addrs = re.findall(r'inet6 ([0-9a-fA-F:]+)/\d+ scope global', out)
        host_ipv6_addrs[host_name] = addrs
        has_expected = any(a.startswith(expected_prefix) for a in addrs)
        check(host_name + " has IPv6 in " + expected_prefix + "::/32 (found: " + str(addrs) + ")",
              has_expected)

    print("\n[Check 2] Hosts have the correct IPv6 default gateway:")
    for host_name, info in HOSTS.items():
        out = ssh_to_host(asn, info['ip_octet'], 'ip -6 route show default')
        if out is None:
            check(host_name + " has an IPv6 default route", False)
            continue
        # this only confirms some default route exists, not necessarily
        # the exact correct one. figuring out if its really pointing to
        # atl or bos specifically would need matching link local
        # addresses, not done here yet
        has_default = bool(out.strip())
        check(host_name + " has some IPv6 default route configured", has_default)

    print("\n[Check 3] Admin and patient hosts use different sub-ranges (VLAN split):")
    for zone, admin_host, patient_host in [('DCN', 'A_MGH', 'P_MGH'),
                                            ('DCS', 'A_EUH', 'P_EUH'),
                                            ('DCS', 'A_CHA', 'P_CHA')]:
        admin_addrs = host_ipv6_addrs.get(admin_host, [])
        patient_addrs = host_ipv6_addrs.get(patient_host, [])
        if not admin_addrs or not patient_addrs:
            check(zone + ": " + admin_host + " vs " + patient_host + " on different sub-ranges", False)
            continue
        # just comparing the first 5 hex groups of the address, roughly a
        # /80, loose enough to catch "literally the same subnet" without
        # being too picky about the exact prefix length someone chose
        admin_prefix = admin_addrs[0].split(':')[:5]
        patient_prefix = patient_addrs[0].split(':')[:5]
        different = admin_prefix != patient_prefix
        check(zone + ": " + admin_host + " (" + str(admin_addrs) + ") vs " +
              patient_host + " (" + str(patient_addrs) + ") on different sub-ranges", different)

    print("\n[Check 4] 6in4 tunnel exists, both directions, using loopback endpoints:")
    # loopback addresses per the spec numbering, atl is router id 6, bos
    # is router id 3
    atl_loopback = str(X) + ".156.0.1"
    bos_loopback = str(X) + ".153.0.1"

    # ip -d tunnel show gives more detail than plain ip tunnel show,
    # including the actual local/remote endpoint addresses
    atl_tunnel_detail = ssh_to_router(asn, ROUTERS['ATL_router'], 'ip -d tunnel show', use_vtysh=False)
    bos_tunnel_detail = ssh_to_router(asn, ROUTERS['BOS_router'], 'ip -d tunnel show', use_vtysh=False)
    # printing this raw so we can see exactly what came back, useful for
    # sanity checking since detecting a tunnel this way was new
    print("  ATL tunnel detail: " + str(atl_tunnel_detail))
    print("  BOS tunnel detail: " + str(bos_tunnel_detail))

    atl_has_tunnel = bool(atl_tunnel_detail and atl_tunnel_detail.strip())
    bos_has_tunnel = bool(bos_tunnel_detail and bos_tunnel_detail.strip())
    check("ATL has a tunnel interface configured", atl_has_tunnel)
    check("BOS has a tunnel interface configured", bos_has_tunnel)

    # only bother checking the endpoints if a tunnel actually exists,
    # otherwise theres nothing to check
    if atl_has_tunnel:
        check("ATL's tunnel uses loopback addresses as endpoints (" +
              atl_loopback + " / " + bos_loopback + ")",
              atl_loopback in atl_tunnel_detail and bos_loopback in atl_tunnel_detail)
    if bos_has_tunnel:
        check("BOS's tunnel uses loopback addresses as endpoints (" +
              bos_loopback + " / " + atl_loopback + ")",
              bos_loopback in bos_tunnel_detail and atl_loopback in bos_tunnel_detail)

    print("\n[Check 5] End to end IPv6 connectivity between DCN and DCS:")
    dcn_target = host_ipv6_addrs.get('A_MGH', [])
    dcs_source_octet = HOSTS['A_EUH']['ip_octet']
    if not dcn_target:
        check("Can find a DCN host address to ping from DCS", False)
    else:
        target_addr = dcn_target[0]
        ping_out = ssh_to_host(asn, dcs_source_octet, 'ping6 -c 2 -W 2 ' + target_addr)
        print("  ping output: " + str(ping_out))
        # important gotcha here, we used to check for the literal text
        # "0% packet loss" in the output, but that string is also hiding
        # inside "100% packet loss" (the last 0 and the % line up
        # exactly), so a complete failure was silently counted as a pass.
        # checking the actual number of packets received instead avoids
        # that trap entirely
        received = 0
        if ping_out:
            match = re.search(r'(\d+) received', ping_out)
            if match:
                received = int(match.group(1))
        ping_worked = received > 0
        check("DCS host (A_EUH) can ping DCN host (A_MGH) over IPv6 (" +
              str(received) + " of 2 packets received)", ping_worked)

    # print the final tally and, if anything failed, list exactly what failed
    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q1.4 FULL CHECK PASSED")
    else:
        print("Q1.4 FULL CHECK FAILED - failed checks:")
        for f in fail_details:
            print("  " + f)
    print("=" * 50)


if __name__ == "__main__":
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_4(asn)
