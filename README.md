# Revenue Command Runner

[![Powered by RustChain](https://img.shields.io/badge/Powered%20by-RustChain-orange)](https://rustchain.org)
Generic cloud execution layer for public opportunity discovery and authoritative settlement/status checks.

Runs every 15 minutes on GitHub Actions and can also be triggered manually. Cloud jobs do not depend on the Mac staying awake, although scheduled GitHub Actions can be delayed or skipped during load.

No credentials, KYC documents, bank data, private keys, or private proposal content are stored here.

## Cloud migration (public/read-only lanes)

- `.github/workflows/run.yml`: cloud opportunity discovery, settlement *observation*, public GitHub bounty radar, decision summary and dashboard issue, every 15 minutes. The radar publishes `bounty_radar.json` as a short-lived Actions artifact and a compact selection in the existing dashboard. Every reward is **advertised/unverified**, not cash received or a funded offer. GitHub source association and repository stars are only screening signals.
- `.github/workflows/public-presence.yml`: refreshes the public Agent402 listing once daily from GitHub-hosted Linux. A positive listing signal is not a paid buyer, transaction or settlement.
- GitHub Actions uses public GitHub data and the repo-scoped `GITHUB_TOKEN`. Neither workflow copies the Mac's existing credentials or its wallet private keys into GitHub.
- `src/local_executor.py` still owns authenticated Dealwork claims, bids, contracts and fulfilment. Its Ollama model runs on the Mac, and `com.nexuseval.executionworker` signs using macOS Keychain/OWS. These **are not cloud-migrated**; cloud execution needs a separately secured credential/key-management and fulfillment redesign, with duplicate-operation prevention and eligibility rules.
- Success metric: a completed cloud run with a fresh `bounty_radar.json` and updated dashboard. Cash settlement and accepted paid deliverables must be verified separately.

## Local account health checks

Run `python3 src/local_health_cycle.py` on the already-authorized worker machine. This hourly Mac job now makes read-only authenticated account checks only. Public Agent402 registration is handled by the separate daily cloud workflow to avoid duplicate registration POSTs. An advisory lock prevents overlapping local checks; the host must be awake and online for those authenticated reads.

Snapshots are private files outside the repository: `~/.openwork/access-audit.json`, `~/.openwork/agent402-refresh.json` and `~/.openwork/access-cycle.json`. Credentials stay in their existing local files; never commit snapshots or keys. A failed or malformed read is UNKNOWN, not a zero balance. A partial public index without a match is UNKNOWN; listing presence never implies paid usage.

Validate with `python3 -W error::ResourceWarning -m unittest discover -s tests`. Existing general-purpose workers are separate from this read-only health cycle.

## Mac continuous scheduling

`src/workday_gate.py -- COMMAND...` is retained as a compatibility wrapper for the installed LaunchAgents and now permits worker starts at every local time. `--check` reports `continuous_24h` without running work.

RunAtLoad and the existing StartInterval/StartCalendarInterval schedules remain unchanged: the authenticated executor runs every minute, the Mac GitHub radar every five minutes (optional fallback once cloud is verified), the health cycle hourly, and the NexusEval worker hourly. Sleep/offline periods still produce no local work; shutdown requires the next login.

`src/workday_awake.py` keeps the Mac from entering idle system sleep continuously while on AC power. The display can sleep, and manual/lid sleep remains possible. On battery or an unknown power source it fails closed and does not force the machine awake. No global power settings are changed.

The pre-24h configuration is backed up under `~/.openwork/continuous-24h-backups/`, in addition to the original workday backups under `~/.openwork/workday-backups/`. Restore the latest backup files and kickstart the LaunchAgents to roll back; account and delivery state are separate and are not erased.
