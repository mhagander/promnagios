# promnagios tools

These simple tools are used to proxy alerts generated in Prometheus AlertManager
into passive alerts in Nagios.

## create_nagios_monitors.py

This tool creates a set of passive nagios monitors based on potential
alerts from Prometheus. All these services will inherit from
`promservice` which should be defined in a different Nagios
configuration file to hold all common settings.

To have a monitor generated, the alert in Prometheus must have an
*annotation* named `hostmap`. This can either be the name of a metric,
in case all hosts with that metric will be included, or it can be a
label-filtered metric in which case only those with that label will be
included. Once the metrics are found, the hostname is extracted from
the label `name`.


## proxy_prometheus_alerts.py

This script should be run as a daemon, and under a user account with
write permissions on the nagios control file. It listens on a specific
http port (localhost only) for AlertManager to make a webhook post
to. Once it receives such a post, it will translate it into a passive
command result in Nagios and write that to the nagios control file.

It also exposes an endpoint at `/ping` which should be monitored
actively from Nagios. It will return *200 OK* when it's
working. This endpoing will also start firing if any alerts are lost
because of an exception during the processing (such as permissions
errors or misconfiguration). To reset such a state, restart the proxy
(which has no other state, so it's safe to restart).
