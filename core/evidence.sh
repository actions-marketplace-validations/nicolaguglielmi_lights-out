#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-evidence: `./go evidence VERSION=<v>` (docs/adr/0081). core/evidence.py
# builds EVIDENCE_DIR/<v>.json from the release log and the ticket's
# document, naming every source and every gap; cosign signs it with the
# plane's key (COSIGN_KEY, default .crew/cosign.key, docs/adr/0025 §2) into
# <v>.json.bundle and verifies it at once. One line on stdout: GO: evidence
# — <path> signed and verified; <n> missing, or NO-GO: evidence — <why>;
# the verify command, for anyone holding the public key, on stderr. Then the
# console frozen from EVIDENCE_LOGBOOK (default .crew/logbook.json) into
# <v>.console.html, signed into its own bundle (docs/adr/0089 §5).
set -eu
name=evidence
. ci/lib.sh
: "${COSIGN_KEY:=.crew/cosign.key}"

out=$(python3 core/evidence.py build) || nogo "${out:-core/evidence.py failed without a reason; see stderr}"
pack=$(printf '%s' "$out" | cut -f1)
gaps=$(printf '%s' "$out" | cut -f2)
rm -f "$pack.bundle"
[ -f "$COSIGN_KEY" ] || nogo "$pack written but not signed: no $COSIGN_KEY; ./go up generates the plane's key"
# Flags as adapters/zot/publish.sh's: no transparency log at L0 (docs/adr/0081 §5).
# shellcheck disable=SC1007 # deliberately empty: cosign's passwordless-key convention
COSIGN_PASSWORD= cosign sign-blob --key "$COSIGN_KEY" --tlog-upload=false --use-signing-config=false \
   --bundle "$pack.bundle" --yes "$pack" >&2 || nogo "cosign sign-blob $pack failed"
pub=${COSIGN_KEY%.key}.pub
cosign verify-blob --key "$pub" --insecure-ignore-tlog --bundle "$pack.bundle" "$pack" >&2 \
  || nogo "$pack signed but its bundle does not verify against $pub"
printf 'evidence: verify with: cosign verify-blob --key %s --insecure-ignore-tlog --bundle %s.bundle %s\n' "$pub" "$pack" "$pack" >&2
# The console as it stands, frozen from the logbook beside the pack and
# signed the same way (docs/adr/0089 §5); no logbook is not a NO-GO.
book=${EVIDENCE_LOGBOOK:-${LOGBOOK_FILE:-.crew/logbook.json}}
snap="${pack%.json}.console.html"
rm -f "$snap" "$snap.bundle"
if ! why=$(python3 core/freeze.py --logbook "$book" --out "$snap" --prefix "evidence pack $(basename "$pack" .json)"); then
  go_with "$pack signed and verified; $gaps missing; no console snapshot: $why"
fi
# shellcheck disable=SC1007 # deliberately empty: cosign's passwordless-key convention
COSIGN_PASSWORD= cosign sign-blob --key "$COSIGN_KEY" --tlog-upload=false --use-signing-config=false \
   --bundle "$snap.bundle" --yes "$snap" >&2 || nogo "cosign sign-blob $snap failed"
cosign verify-blob --key "$pub" --insecure-ignore-tlog --bundle "$snap.bundle" "$snap" >&2 \
  || nogo "$snap signed but its bundle does not verify against $pub"
go_with "$pack signed and verified; $gaps missing; console snapshot signed"
