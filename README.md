# Revenue Command Runner

[![Powered by RustChain](https://img.shields.io/badge/Powered%20by-RustChain-orange)](https://rustchain.org)
Generic cloud execution layer for public opportunity discovery and authoritative settlement/status checks.

Runs every 5 minutes in GitHub Actions and can also be triggered manually.

No credentials, KYC documents, bank data, private keys, or private proposal content are stored here.

## Local account health checks

Run `python3 src/local_health_cycle.py` on the already-authorized worker machine. The cycle makes read-only account checks and a public Agent402 registration refresh at most once per 24 hours. A scheduler may invoke it hourly; an advisory lock prevents overlapping cycles. The host must be awake and online.

Snapshots are private files outside the repository: `~/.openwork/access-audit.json`, `~/.openwork/agent402-refresh.json` and `~/.openwork/access-cycle.json`. Credentials stay in their existing local files; never commit snapshots or keys. A failed or malformed read is UNKNOWN, not a zero balance. A partial public index without a match is UNKNOWN; listing presence never implies paid usage.

Validate with `python3 -W error::ResourceWarning -m unittest discover -s tests`. Existing general-purpose workers are separate from this read-only health cycle.

## Mac workday scheduling

`src/workday_gate.py -- COMMAND...` starts an existing worker only between 08:00 (inclusive) and 20:00 (exclusive), every day in Asia/Kolkata. Already-running work may finish. `--check` reports the gate without running work.

Use RunAtLoad for login startup and StartCalendarInterval for normal cadence and wake catch-up; launchd coalesces missed calendar firings into one event. The health, worker and radar agents retain their hourly, two-minute or five-minute cadence. Sleep/offline periods produce no local work; shutdown requires the next login.

`src/workday_awake.py` holds an idle-system-sleep assertion only during that window on AC power. The display can sleep. Unplugging, power-read failure or 20:00 releases the tracked assertion; manual/lid sleep remains possible. Launch it with RunAtLoad and a wildcard StartCalendarInterval. Both helper processes are unprivileged and no global power settings are changed.

Installation backs up pre-existing LaunchAgent plists under `~/.openwork/workday-backups/` and records their location in `~/.openwork/workday-setup.json`. To undo, unload the new awake agent, unload each changed agent, restore its original plist from that backup and bootstrap the original agents. Restoring does not erase account or delivery state.
