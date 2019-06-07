#!/usr/bin/env python3
#
# Generate passive monitors for alerts from Prometheus into Nagios.
#
# Copyright 2019, PostgreSQL Infrastructure Team
# Author: Magnus Hagander
#

import requests
import io
import argparse
import sys
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create nagios alerts from prometheus monitors"
    )
    parser.add_argument('--prometheus',
                        help='Base URL of prometheus',
                        default='http://localhost:9090')
    parser.add_argument('--target',
                        help='Filename to write to')
    parser.add_argument('--hostsuffix',
                        help='Add suffix to hostnames')
    args = parser.parse_args()

    if not args.prometheus or not args.target:
        print("Must specify both prometheus base and target file")
        sys.exit(2)

    def _fetch_hostlist(expr):
        r = requests.get(
            '{0}/api/v1/query?query={1}'.format(args.prometheus, expr)
        )
        return list(set(
            [i['metric']['name'] for i in r.json()['data']['result']]
        ))

    monitors = []

    r = requests.get('{0}/api/v1/rules'.format(args.prometheus))
    rulegroups = r.json()['data']['groups']
    for group in rulegroups:
        for rule in group['rules']:
            if rule['type'] != 'alerting':
                continue
            if 'hostmap' not in rule['annotations']:
                continue

            monitors.append({
                'name': rule['name'],
                'hosts': _fetch_hostlist(rule['annotations']['hostmap']),
            })

    s = io.StringIO()
    for m in sorted(monitors, key=lambda x: x['name']):
        for h in sorted(m['hosts']):
            if args.hostsuffix:
                h = "{0}.{1}".format(h, args.hostsuffix)
            s.write("""define service {{
   host_name             {0}
   service_description   {1}
   use                   promservice
}}
""".format(h, m['name']))

    if os.path.isfile(args.target):
        with open(args.target, 'r') as f:
            old = f.read()
    else:
        old = ""

    if old != s.getvalue():
        # File changed!
        with open("{0}.new".format(args.target), "w") as f:
            f.write(s.getvalue())
        os.rename("{0}.new".format(args.target), args.target)
        sys.exit(1)

    # No change, so just exit