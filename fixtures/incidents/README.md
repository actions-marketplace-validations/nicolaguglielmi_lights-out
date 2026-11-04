# Captured incidents

Incident documents (docs/adr/0044 §1) built by `./go incident` from a real release. The ops-triage role reads one and files a post mortem; `./go demo-postmortem` replays the role's recording of it, and `./go record-postmortem PROFILE=l1` makes that recording. Nothing here is written by hand.

## demo-rollback.json

Captured 2026-11-04 from `./go demo-rollback` on a full clone of the M22 branch (commit 3dc46d1), podman 5 machine on macOS, L0, no key. The commands, in the clone:

```
./go up
./go demo-rollback            # 10:32:07Z to 10:33:33Z
./go incident NAME=demo-rollback FROM=2026-11-04T10:32:07Z TO=2026-11-04T10:33:33Z LOGS=.crew/demo-rollback.log
```

`.crew/demo-rollback.log` is the run's stderr lines matching `^\[(launchpad|demo-rollback)\] |^slo: `. The release record is that run's `.crew/release.json` verbatim: canary `0.2.0-waitlist` rolled back at the 5% stage on `error_rate`. The numbers are that run's; a fresh run gives different ones, which is why the demo keys on this file and not on a live record. `chain` is `null`: `demo-rollback` releases a version directly, with no ticket and no PR.
