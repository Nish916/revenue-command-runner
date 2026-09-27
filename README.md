# Revenue Command Runner
Generic cloud execution layer for public opportunity discovery and authoritative settlement/status checks.

Runs every 5 minutes in GitHub Actions and can also be triggered manually.

No credentials, KYC documents, bank data, private keys, or private proposal content are stored here.

## Local account health checks

Run `python3 src/local_health_cycle.py` on the already-authorized worker machine. The cycle makes read-only account checks and a public Agent402 registration refresh at most once per 24 hours. A scheduler may invoke it hourly; an advisory lock prevents overlapping cycles. The host must be awake and online.

Snapshots are private files outside the repository: `~/.openwork/access-audit.json`, `~/.openwork/agent402-refresh.json` and `~/.openwork/access-cycle.json`. Credentials stay in their existing local files; never commit snapshots or keys. A failed or malformed read is UNKNOWN, not a zero balance. A partial public index without a match is UNKNOWN; listing presence never implies paid usage.

Validate with `python3 -W error::ResourceWarning -m unittest discover -s tests`. Existing general-purpose workers are separate from this read-only health cycle.
