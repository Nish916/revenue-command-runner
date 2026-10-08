# Revenue Command Runner

[![Powered by RustChain](https://img.shields.io/badge/Powered%20by-RustChain-orange)](https://rustchain.org)
Generic cloud execution layer for public opportunity discovery and authoritative settlement/status checks.

Runs every 5 minutes in GitHub Actions and can also be triggered manually.

No credentials, KYC documents, bank data, private keys, or private proposal content are stored here.

## Local account health checks

Run `python3 src/local_health_cycle.py` on the already-authorized worker machine. The cycle makes read-only account checks and a public Agent402 registration refresh at most once per 24 hours. A scheduler may invoke it hourly; an advisory lock prevents overlapping cycles. The host must be awake and online.

Snapshots are private files outside the repository: `~/.openwork/access-audit.json`, `~/.openwork/agent402-refresh.json` and `~/.openwork/access-cycle.json`. Credentials stay in their existing local files; never commit snapshots or keys. A failed or malformed read is UNKNOWN, not a zero balance. A partial public index without a match is UNKNOWN; listing presence never implies paid usage.

Validate with `python3 -W error::ResourceWarning -m unittest discover -s tests`. Existing general-purpose workers are separate from this read-only health cycle.

## Mac continuous scheduling

`src/workday_gate.py -- COMMAND...` is retained as a compatibility wrapper for the installed LaunchAgents and now permits worker starts at every local time. `--check` reports `continuous_24h` without running work.

RunAtLoad and the existing StartInterval/StartCalendarInterval schedules remain unchanged: the authenticated executor runs every minute, the GitHub radar every five minutes, the health cycle hourly, and the NexusEval worker hourly. Sleep/offline periods still produce no local work; shutdown requires the next login.

`src/workday_awake.py` keeps the Mac from entering idle system sleep continuously while on AC power. The display can sleep, and manual/lid sleep remains possible. On battery or an unknown power source it fails closed and does not force the machine awake. No global power settings are changed.

The pre-24h configuration is backed up under `~/.openwork/continuous-24h-backups/`, in addition to the original workday backups under `~/.openwork/workday-backups/`. Restore the latest backup files and kickstart the LaunchAgents to roll back; account and delivery state are separate and are not erased.
