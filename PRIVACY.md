# Privacy boundary

The D1 database stores only:

- random batch IDs for short-lived retry deduplication;
- UTC date ranges and coarse major/minor netlab versions;
- finite-vocabulary metric dimensions and item names;
- aggregate observations, instances, and maxima.

The service does not create a user account, installation identifier, browser
session, or cross-batch identifier. It does not store request bodies, source
IP addresses, user agents, topology contents, topology or node names,
hostnames, paths, addresses, or custom object names.

Pydantic validation errors are filtered before being returned. They include a
field location, error type, and message, but do not echo the rejected input
value. Structurally valid custom labels are normalized to `_custom` or
`_other` before database storage.

Cloudflare necessarily processes connection metadata to deliver and protect
the HTTPS service. Worker observability is disabled in the supplied
configuration, and the Worker contains no application logging calls.

Accepted batch IDs are deleted after 30 days by default. Aggregate rows remain
until the operator applies its published retention policy.
