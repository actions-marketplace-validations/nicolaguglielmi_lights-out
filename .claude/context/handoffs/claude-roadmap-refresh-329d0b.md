# Handoff — ROADMAP.md refreshed to main (docs only)

Branch `claude/roadmap-refresh-329d0b`, cut from main b4b1590. Not merged.
Only `ROADMAP.md` changed (plus this note).

## What changed

- **Done:** 26 rows added, each one line with its ADR link, in the file's
  style: M17 third slice (0071), M25 (0051), M26 (0052), M31 second slice
  (0064), M39 (0069), M42 (0073), M43 (0072), release machinery
  (0074-0077), M24 phases A-D, M45-M50 (0078-0083), M51 (0084), M32 (0058),
  M52-M54 (0085-0087), M55 (0088), M56 (0089), M57 (0090), and the
  releases 0.4.0, 0.5.0, 0.6.0, 0.7.0 (tag dates from the checklist; 0.7.0
  on the Marketplace 2026-11-15).
- **Next:** the stale 0.3.0 text and the M24 and M32 bullets are gone; the
  sprint of 2026-11-16 (M58-M63) is listed in progress, one line each,
  with ADRs 0091, 0092, 0093, 0095, 0096 as plain text because they are
  not on main yet (M61 has no ADR in the brief). M24's remaining legs:
  OpenAI not run, GLM after M59. M32's leftovers moved under M62.
- **Later:** M16 dropped (built, in Done); the security-scanning item
  dropped (built, M43); M17 updated with the network, flow strip, role
  matrix and burn.
- **When someone needs it:** unchanged (M44, M8, M10).
- Nothing new added: no theme beyond the public ROADMAP and PLAN and the
  sprint, no voting, no Discussions.

## Sources

Every number comes from `docs/releases/`, the ADRs, `docs/PLAN.md`
(status notes of M24, M26, M51) or `docs/launch/checklist.md`. The M58-M63
lines come from the coordinator's brief only; check them against the
sprint's own ADRs when they land.

## Proof

`MAP_EXCLUDE='docs/PLAN.md docs/plans/* .claude/*' sh ci/docs-drift.sh`:
`GO: docs-drift`.
