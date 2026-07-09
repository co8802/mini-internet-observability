import sys
import ipaddress
from suzieq.sqobjects import get_sqobject

# this script checks q1.1, the l2 dcs vlan setup
# it looks at atl's two vlan interfaces and makes sure they exist, are up, and have the right ips

def check_q1_1(asn):
    # turn the group number into suzieq's namespace format, like 3 becomes as-03
    ns = "as-{:02d}".format(asn)
    X = asn

    passed = 0
    failed = 0
    results = []

    # small helper so we dont repeat if/else everywhere
    # just call check("description", true or false) and it logs and counts it
    def check(name, condition):
        nonlocal passed, failed
        if condition:
            results.append("  PASS: " + name)
            passed += 1
        else:
            results.append("  FAIL: " + name)
            failed += 1

    cfg = './suzieq-cfg.yml'

    # get a handle to suzieq's interface table, this is the proper way to pull data
    # never read parquet files directly with pandas glob, suzieq handles staleness for us
    iface_tbl = get_sqobject('interface')

    # the assignment only guarantees the whole dcs block as one /23, x.200.0.0/23
    # groups are free to split that /23 into two /24s or leave it as one range
    # so instead of hardcoding two separate /24s, we just check membership in the /23
    dcs_net = ipaddress.IPv4Network(str(X) + '.200.0.0/23')

    print("=" * 50)
    print("Q1.1 L2 DCS Verification - AS " + str(asn))
    print("=" * 50)

    # pull every interface belonging to atl's router for this group
    df = iface_tbl(config_file=cfg).get(namespace=[ns], hostname=['ATL_router'])

    print("\n[Check 1] ATL VLAN interfaces exist and are up:")

    # filter down to just the two vlan interfaces we care about
    atl_l2_10 = df[df['ifname'] == 'ATL-L2.10']
    atl_l2_20 = df[df['ifname'] == 'ATL-L2.20']

    # if a student never configured the interface, this table will just be empty
    check("ATL-L2.10 exists", len(atl_l2_10) > 0)
    check("ATL-L2.20 exists", len(atl_l2_20) > 0)

    # only check "is it up" if the interface actually exists, otherwise this would crash
    if len(atl_l2_10) > 0:
        check("ATL-L2.10 is up", 'up' in atl_l2_10['state'].values)
    if len(atl_l2_20) > 0:
        check("ATL-L2.20 is up", 'up' in atl_l2_20['state'].values)

    print("\n[Check 2] ATL VLAN interfaces have correct IPs:")

    # an interface can have more than one ip assigned to it, so we loop through the whole list
    # and check if any of them land inside the expected subnet
    def has_ip_in_network(rows, network):
        for _, row in rows.iterrows():
            for ip in row['ipAddressList']:
                try:
                    addr = ipaddress.IPv4Interface(ip).ip
                    if addr in network:
                        return True
                except:
                    # skip anything that isnt a valid ipv4 address, like ipv6 entries
                    pass
        return False

    if len(atl_l2_10) > 0:
        check("ATL-L2.10 has IP in DCS block (" + str(X) + ".200.0.0/23)",
              has_ip_in_network(atl_l2_10, dcs_net))
    if len(atl_l2_20) > 0:
        check("ATL-L2.20 has IP in DCS block (" + str(X) + ".200.0.0/23)",
              has_ip_in_network(atl_l2_20, dcs_net))

    print("\n" + "=" * 50)
    print("Results: " + str(passed) + " passed, " + str(failed) + " failed")
    if failed == 0:
        print("Q1.1 PASSED")
    else:
        print("Q1.1 FAILED - failed checks:")
        for r in results:
            if 'FAIL' in r:
                print(r)
    print("=" * 50)

if __name__ == "__main__":
    # default to group 3 if no group number is passed in
    asn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    check_q1_1(asn)
