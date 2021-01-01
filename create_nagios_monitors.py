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
import time

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
    parser.add_argument('--dependon',
                        help='Create service dependency')
    parser.add_argument('--refreshstate',
                        help='Generate service refreshes to specified commandfile')
    args = parser.parse_args()

    if not args.prometheus or not args.target:
        print("Must specify both prometheus base and target file")
        sys.exit(2)

    def _fetch_hostlist(expr):
        r = requests.get(
            '{0}/api/v1/series'.format(args.prometheus), params={
                'match[]': expr,
                'start': time.time() - 12*3600, # Any host that has been seen in the past 12 hours
            }
        )
        return list(set(
            [i['name'] for i in r.json()['data']]
        ))

    r = requests.get('{0}/api/v1/targets'.format(args.prometheus))
    targets = set(
        [t['labels']['name'] for t in r.json()['data']['activeTargets']]
    )

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

    r = requests.get('{0}/api/v1/alerts'.format(args.prometheus))
    alerts = r.json()['data']['alerts']
    activealerts = [(a['labels']['name'], a['labels']['alertname']) for a in alerts if a['state'] == 'firing']

    s = io.StringIO()
    refreshcommands = io.StringIO()
    t = time.time()

    for m in sorted(monitors, key=lambda x: x['name']):
        for h in sorted(m['hosts']):
            if h not in targets:
                continue

            shorthost = h  # Save away before we rewrite it

            if args.hostsuffix:
                h = "{0}.{1}".format(h, args.hostsuffix)
            s.write("""define service {{
   host_name             {0}
   service_description   {1}
   use                   promservice
}}
""".format(h, m['name']))
            if args.dependon:
                s.write("""define servicedependency{{
   host_name             {0}
   service_description   ping
   dependent_host_name   {1}
   dependent_service_description {2}
   execution_failure_criteria    w,u,c
   notification_failure_criteria w,u,c
}}
""".format(h, h, m['name']))

            # If this service is *not* alerting, then refresh it. If it *is* alerting, we ignore it because
            # AlertManager is going to push the actual alert with refresh.
            if (shorthost, m['name']) not in activealerts:
                refreshcommands.write(
                    "[{0}] PROCESS_SERVICE_CHECK_RESULT;{1};{2};{3};{4}\n".format(
                        t, h, m['name'], 0, "Refreshed OK",
                    ))

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

    if args.refreshstate:
        # We'll refresh the state of both old and new services, to be sure.
        # Nagios will just ignore the unknown ones.
        s = io.StringIO()
        with open(args.refreshstate, 'w') as f:
            f.write(refreshcommands.getvalue())
