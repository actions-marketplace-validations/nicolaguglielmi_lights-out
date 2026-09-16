# SPDX-License-Identifier: Apache-2.0
#
# Runs inside the workbench container. Use ./go <target> from the host.
# Profiles select the adapters (docs/adr/0001-profiles-and-single-makefile.md).

SHELL := /bin/sh
.DEFAULT_GOAL := help

PROFILE ?= l0
include profiles/$(PROFILE).env
-include .env
export

# docker-compose over the podman socket builds through the classic /build
# API; pinning this avoids compose spawning a buildkitd container
# (docs/adr/0010).
DOCKER_BUILDKIT := 0
export DOCKER_BUILDKIT

COMPOSE := docker-compose

# Workbench reaches a port compose publishes on the engine host through this
# alias (docs/adr/0011, 0012 §6); it is the one place the hostname is written.
PLANE_HOST ?= host.containers.internal
APP_URL ?= http://$(PLANE_HOST):8080
export PLANE_HOST APP_URL

# Seconds each adapters/<name>/ready.sh polls before giving up: 4x the 15 s a
# cold plane took to answer at M2 close (docs/adr/0012 §6, HANDOFF).
READY_TIMEOUT ?= 60
export READY_TIMEOUT

# Adapters that run as plane services at this profile, in readiness order.
PLANE_ADAPTERS := $(CODE_HOST) $(DELIVERY) $(METRICS) $(FLAGS) $(REGISTRY) $(EVENT_BUS) $(STATE_STORE)

# The gemini-cli worker's compose service writes into its workspace bind
# mount as this uid:gid, so workbench (running as the host user under
# docker, root under rootless podman) can still read and commit what it
# wrote (docs/adr/0017 §3).
CREW_UID := $(shell id -u)
CREW_GID := $(shell id -g)
export CREW_UID CREW_GID

# M3 release controller (docs/adr/0013, 0014). Workbench reaches the Envoy
# admin API the same way it reaches every other plane port (PLANE_HOST).
ENVOY_ADMIN_URL ?= http://$(PLANE_HOST):9901
export ENVOY_ADMIN_URL

# The L0 "failing version": app/flags/flags.json targets `waitlist` on for
# exactly this string (docs/adr/0013 §1). A drift between the two makes
# demo-rollback's and demo-hold's assertions fail loudly instead of quietly
# passing for the wrong reason.
CANARY_VERSION ?= 0.2.0-waitlist
export CANARY_VERSION

# Seconds launchpad holds a shift before calling verify/slo.sh: equal to the
# slo.promql window, so a stage's numbers describe only this stage's canary
# (docs/adr/0013 §2, §5).
STAGE_SECONDS ?= 60
export STAGE_SECONDS

# Plan §2's ceiling on `./go demo` reaching the automatic rollback, timed by
# ./go from before engine-compat, where the cold pulls happen (docs/adr/0013
# §7). 0 disables the verdict; the elapsed time is still printed.
DEMO_BUDGET_SECONDS ?= 900

# The PR gates (docs/adr/0015 §2), cheap and stable ones first, the ones
# needing a fresh image build or a live network last; `gates` stops at the
# first NO-GO. `secrets` reuses the existing repo-wide ci/secrets.sh (it
# already covers history plus the working tree for any range); every other
# name is gates/<name>.sh.
GATES := risk secrets deps sast test mutation

# Where a gate run's data beyond its one-line verdict lands: risk.json,
# mutation.json, and gates' own verdict.env (docs/adr/0015 §2). Gitignored;
# a fresh gates run wipes and recreates it.
GATES_OUT ?= .gates-out
export GATES_OUT

# Milestone stubs. A target whose milestone has not arrived fails loudly.
define not_yet
	@printf 'NO-GO: %s arrives with %s. Nothing runs yet.\n' "$(1)" "$(2)" >&2; exit 1
endef

.PHONY: help
help: ## List the targets
	@printf 'lights-out  (profile: %s)\n\n' "$(PROFILE)"
	@awk 'BEGIN{FS=":.*## "} /^[a-z][a-z0-9-]*:.*## /{printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@for c in $(CI_CHECKS); do printf '  %-16s %s\n' "ci-$$c" "one self-check, see ci/$$c.sh"; done
	@printf '\n  Host side, via ./go only:\n  %-16s %s\n  %-16s %s\n  %-16s %s\n' \
		engine-compat "host-side engine gate: versions, then up and smoke (ci/engine-compat.sh)" \
		shell "interactive shell inside workbench" clean "remove the workbench image"

# Self-checks run by `ci`, in order. engine-compat runs on the host (ADR 0004, ADR 0012 §5), never here.
CI_CHECKS := secrets lint shell help readme gitea-compat profiles compose core-tests hooks harness tower contract

.PHONY: ci
ci: $(addprefix ci-,$(CI_CHECKS)) ## Repo self-checks (ADR 0002), same on laptop and CI
	@printf 'GO: ci\n'

.PHONY: ci-%
ci-%:
	@sh ci/$*.sh

.PHONY: demo
demo: ## The demo, as far as the current milestone takes it (ADR 0003, 0013 §7)
	@printf '[demo] engine-compat: done on the host by ./go before this run\n' >&2
	@printf '[demo] ci (M2): running\n'
	@$(MAKE) --no-print-directory ci
	@$(MAKE) --no-print-directory up
	@printf '[demo] up: L0 plane, %s\n' "$(PLANE_ADAPTERS)" >&2
	@$(MAKE) --no-print-directory smoke
	@printf '[demo] smoke: a meetup created through Envoy at %s\n' "$(APP_URL)" >&2
	@$(MAKE) --no-print-directory verify
	@printf '[demo] verify: metric shape only; canary vs stable is evaluated inside demo-rollback below\n' >&2
	@$(MAKE) --no-print-directory demo-rollback
	@printf '[demo] deploy, verify (canary vs stable), rollback: proved by demo-rollback above (docs/adr/0013, 0014)\n' >&2
	@$(MAKE) --no-print-directory e2e
	@printf '[demo] e2e: ticket → PR → CI → merge → canary → verify NO-GO → rollback, audited (docs/adr/0019)\n' >&2
	@printf 'lights-out: app at %s, Gitea at http://localhost:3000, Prometheus at http://localhost:9090\n' "$(APP_URL)" >&2
	@now=$$(date +%s); t0=$${LIGHTS_OUT_T0:-$$now}; elapsed=$$((now - t0)); \
	if [ "$$elapsed" -lt 0 ]; then \
		printf 'GO: demo, milestone M6, rollback reached but not timed: the engine clock is %ss behind the host, budget %ss unverified (plan §2)\n' "$$((0 - elapsed))" "$(DEMO_BUDGET_SECONDS)"; \
		exit 0; \
	fi; \
	if [ "$(DEMO_BUDGET_SECONDS)" -gt 0 ] && [ "$$elapsed" -gt "$(DEMO_BUDGET_SECONDS)" ]; then \
		printf 'NO-GO: demo — rollback reached, but %ss > %ss budget (plan §2)\n' "$$elapsed" "$(DEMO_BUDGET_SECONDS)"; \
		exit 1; \
	fi; \
	printf 'GO: demo, milestone M6, %ss to rollback (budget %ss, plan §2)\n' "$$elapsed" "$(DEMO_BUDGET_SECONDS)"

.PHONY: up
up: ## Start the L0 plane in compose and wait until every adapter is ready (docs/adr/0012 §6)
	@$(COMPOSE) up -d --build >&2
	@for a in $(PLANE_ADAPTERS); do \
		[ -f "adapters/$$a/ready.sh" ] || { printf 'lights-out: adapters/%s/ready.sh is missing\n' "$$a" >&2; exit 1; }; \
		printf 'lights-out: waiting for %s\n' "$$a" >&2; \
		sh "adapters/$$a/ready.sh" || exit 1; \
	done
	@printf 'lights-out: plane is up, app at %s\n' "$(APP_URL)" >&2

.PHONY: smoke
smoke: ## Sign up, log in and create a meetup through Envoy (app/smoke.sh)
	@sh app/smoke.sh

.PHONY: down
down: ## Stop the app, including a held canary revision if one is running
	@$(COMPOSE) --profile test --profile canary down

.PHONY: test
test: ## Run the backend test suite against compose Postgres (docs/adr/0010)
	$(COMPOSE) --profile test run --rm --build backend-test

.PHONY: verify
verify: ## Check verify/slo.promql against the live app (M1: metric shape only, evaluated at M3)
	@APP_URL="$(APP_URL)" sh verify/metric-shape.sh

# Each gate's own stdout line is the verdict; a gate's stderr (compose
# builds, pytest, bandit, cosmic-ray) streams straight through, live, never
# captured here. `gates` writes $(GATES_OUT)/verdict.env in the exact shape
# gates/fixtures/*/expect uses, so demo-gates can diff the two instead of
# re-parsing anything (docs/adr/0015 §2, §6).
.PHONY: gates
gates: ## Judge a PR: BASE=<ref> HEAD=<ref> — risk, secrets, deps, sast, test, mutation (docs/adr/0015, 0016)
	@rm -rf "$(GATES_OUT)" && mkdir -p "$(GATES_OUT)"
	@failed=""; failreason=""; \
	for g in $(GATES); do \
		case "$$g" in secrets) script=ci/secrets.sh ;; *) script=gates/$$g.sh ;; esac; \
		out=$$(BASE="$(BASE)" HEAD="$(HEAD)" sh "$$script"); \
		case "$$out" in \
			"GO: $$g") ;; \
			*) failed=$$g; failreason=$$out; break ;; \
		esac; \
	done; \
	level=unknown; decision=unknown; \
	if [ -f "$(GATES_OUT)/risk.json" ]; then \
		level=$$(jq -r .level "$(GATES_OUT)/risk.json"); \
		decision=$$(jq -r .decision "$(GATES_OUT)/risk.json"); \
	fi; \
	mt=""; \
	if [ -f "$(GATES_OUT)/mutation.json" ]; then \
		mt=$$(jq -r 'if .total == 0 then "zero" else "some" end' "$(GATES_OUT)/mutation.json"); \
	fi; \
	if [ -n "$$failed" ]; then \
		{ printf 'GATES=NO-GO\n'; printf 'FAILED=%s\n' "$$failed"; \
		  printf 'RISK_LEVEL=%s\n' "$$level"; printf 'RISK_DECISION=%s\n' "$$decision"; \
		  if [ -n "$$mt" ]; then printf 'MUTATION_TOTAL=%s\n' "$$mt"; fi; \
		} > "$(GATES_OUT)/verdict.env"; \
		printf 'NO-GO: gates — %s: %s\n' "$$failed" "$$failreason"; \
		exit 1; \
	fi; \
	{ printf 'GATES=GO\n'; printf 'RISK_LEVEL=%s\n' "$$level"; printf 'RISK_DECISION=%s\n' "$$decision"; \
	  if [ -n "$$mt" ]; then printf 'MUTATION_TOTAL=%s\n' "$$mt"; fi; \
	} > "$(GATES_OUT)/verdict.env"; \
	printf 'GO: gates — risk %s, %s\n' "$$level" "$$decision"

# Proves every gate can both GO and NO-GO, on committed fixtures, not just
# once in a build log (docs/adr/0015 §6; the demo-hold lesson, docs/adr/0014:
# a verify wired to always pass -- or fail -- would pass its own demo too).
# Each fixture is a real commit applied by `git am` in its own throwaway
# worktree off HEAD, judged as the range HEAD..<applied>, then discarded.
.PHONY: demo-gates
demo-gates: ## Prove every PR gate GO and NO-GO on the committed fixtures (docs/adr/0015 §6)
	@git worktree prune
	@main_sha=$$(git rev-parse HEAD); \
	tmp1=$$(mktemp); tmp2=$$(mktemp); \
	trap 'rm -f "$$tmp1" "$$tmp2"' EXIT; \
	for f in gates/fixtures/*/; do \
		name=$$(basename "$$f"); \
		wt=$$(mktemp -d)/wt; \
		err=$$(git worktree add --detach "$$wt" HEAD 2>&1 >/dev/null) || { \
			printf 'NO-GO: demo-gates — %s: git worktree add failed: %s\n' "$$name" "$$err"; exit 1; \
		}; \
		if ! git -C "$$wt" -c user.name=lights-out-fixtures -c user.email=fixtures@lights-out.invalid \
				am "$$f"*.patch >/dev/null 2>&1; then \
			git -C "$$wt" am --abort >/dev/null 2>&1 || true; \
			git worktree remove --force "$$wt"; \
			printf 'NO-GO: demo-gates — %s does not apply; regenerate\n' "$$name"; \
			exit 1; \
		fi; \
		head_sha=$$(git -C "$$wt" rev-parse HEAD); \
		out=$$( (cd "$$wt" && $(MAKE) --no-print-directory gates BASE="$$main_sha" HEAD="$$head_sha") ); \
		printf '[demo-gates] %s: %s\n' "$$name" "$$out" >&2; \
		sort "$$wt/$(GATES_OUT)/verdict.env" > "$$tmp1" 2>/dev/null || : > "$$tmp1"; \
		sort "$$f/expect" > "$$tmp2"; \
		if ! diff -q "$$tmp1" "$$tmp2" >/dev/null 2>&1; then \
			printf '[demo-gates] %s: verdict mismatch\n  got:  %s\n  want: %s\n' "$$name" \
				"$$(tr '\n' ' ' < "$$wt/$(GATES_OUT)/verdict.env" 2>/dev/null || echo '(no verdict.env)')" \
				"$$(tr '\n' ' ' < "$$f/expect")" >&2; \
			git worktree remove --force "$$wt"; \
			printf 'NO-GO: demo-gates — %s does not match expect\n' "$$name"; \
			exit 1; \
		fi; \
		git worktree remove --force "$$wt"; \
	done; \
	printf 'GO: demo-gates\n'

.PHONY: assign
assign: ## Turn a ticket into a PR: TICKET=<id> [ROLE=dev-worker] (docs/adr/0017 §4)
	@TICKET="$(TICKET)" ROLE="$(ROLE)" sh core/crew.sh

# Shared by demo-crew and record (docs/adr/0017 §6): runs assign, then
# the CI step the tower uses (core/steps/ci.sh, docs/adr/0019 §1) on the
# range .crew/<ticket>/pr-opened.env records — fetch from CODE_HOST,
# throwaway worktree, `make gates`, verdict posted as a commit status —
# leaving the verdict at $(GATES_OUT)/verdict.env at the repo root; the
# caller decides what a GO or a NO-GO means. Always exits 0 past assign;
# a gates NO-GO is data, not a Makefile failure.
.PHONY: crew-run
crew-run:
	@rm -f "$(GATES_OUT)/verdict.env"
	@role="$(ROLE)"; [ -n "$$role" ] || role=dev-worker; \
	$(MAKE) --no-print-directory assign TICKET="$(TICKET)" ROLE="$$role" >&2 || { \
		printf 'NO-GO: crew-run — assign did not produce a PR\n'; exit 1; \
	}; \
	. ".crew/$(TICKET)/pr-opened.env"; \
	TICKET="$(TICKET)" PR_NUMBER="$$PR_NUMBER" BASE_SHA="$$BASE_SHA" HEAD_SHA="$$HEAD_SHA" \
		sh core/steps/ci.sh >/dev/null || { \
		printf 'NO-GO: crew-run — the CI step did not reach a verdict\n'; exit 1; \
	}

.PHONY: demo-crew
demo-crew: ## Prove ticket 0001 becomes a PR that passes the M4 gates (docs/adr/0017; the M5 acceptance command)
	@$(MAKE) --no-print-directory up
	@$(MAKE) --no-print-directory crew-run TICKET=0001 ROLE=dev-worker
	@expect=fixtures/0001/dev-worker/expect; \
	if [ ! -f "$$expect" ]; then \
		printf 'NO-GO: demo-crew — no %s; run ./go record TICKET=0001 PROFILE=l1 first\n' "$$expect"; exit 1; \
	fi; \
	tmp1=$$(mktemp); tmp2=$$(mktemp); \
	sort "$(GATES_OUT)/verdict.env" > "$$tmp1" 2>/dev/null || : > "$$tmp1"; \
	sort "$$expect" > "$$tmp2"; \
	if ! diff -q "$$tmp1" "$$tmp2" >/dev/null 2>&1; then \
		printf '[demo-crew] verdict mismatch\n  got:  %s\n  want: %s\n' \
			"$$(tr '\n' ' ' < "$(GATES_OUT)/verdict.env" 2>/dev/null || echo '(no verdict.env)')" \
			"$$(tr '\n' ' ' < "$$expect")" >&2; \
		rm -f "$$tmp1" "$$tmp2"; \
		printf 'NO-GO: demo-crew — verdict does not match fixtures/0001/dev-worker/expect\n'; exit 1; \
	fi; \
	rm -f "$$tmp1" "$$tmp2"; \
	printf 'GO: demo-crew\n'

# Records the one real L1 run this ADR calls for (docs/adr/0017 §6): the
# fixture L0 replays forever after. Refuses at L0 ("recording a replay is
# circular" — AGENT_HARNESS=replay would replay the fixture it is trying to
# create) and refuses a run that does not pass the gates (kept under
# .crew/<ticket> for study; the attempt is not silently retried here, and
# HANDOFF records how many attempts the recorded run took).
.PHONY: record
record: ## Run a ticket for real at L1 and save the fixture: TICKET=<id> [ROLE=dev-worker] (docs/adr/0017 §6)
	@if [ "$(AGENT_HARNESS)" != "gemini-cli" ]; then \
		printf 'NO-GO: record — recording a replay is circular; PROFILE=l1\n'; exit 1; \
	fi
	@$(MAKE) --no-print-directory up
	@role="$(ROLE)"; [ -n "$$role" ] || role=dev-worker; \
	$(MAKE) --no-print-directory crew-run TICKET="$(TICKET)" ROLE="$$role" || { \
		printf 'NO-GO: record — ticket %s did not reach the gates; see the crew-run output above\n' "$(TICKET)"; \
		exit 1; \
	}; \
	gates_verdict=$$(grep '^GATES=' "$(GATES_OUT)/verdict.env" 2>/dev/null | cut -d= -f2); \
	if [ "$$gates_verdict" != "GO" ]; then \
		printf 'NO-GO: record — ticket %s did not pass the gates (GATES=%s); kept under .crew/%s for study\n' \
			"$(TICKET)" "$${gates_verdict:-unknown}" "$(TICKET)"; \
		exit 1; \
	fi; \
	dest="fixtures/$(TICKET)/$$role"; \
	mkdir -p "$$dest"; \
	cp .crew/$(TICKET)/out/* "$$dest/" 2>/dev/null || true; \
	cp "$(GATES_OUT)/verdict.env" "$$dest/expect"; \
	printf 'lights-out: fixture written to %s\n' "$$dest" >&2; \
	printf 'GO: record\n'

# Not a gate: a measurement. MUTATION_LINES=all tells tests/mutation/run.sh
# to skip the line filter and mutate the whole package, so this is the
# number policy/merge.env's MUTATION_BASELINE cites, with its provenance
# comment (commit, date, tool version, mutant count, wall time) written by
# hand after reading this target's output (docs/adr/0015 §3).
.PHONY: mutation-baseline
mutation-baseline: ## Whole-package mutation score, for MUTATION_BASELINE's provenance (docs/adr/0015 §3)
	@$(COMPOSE) -p lo-mutation-baseline --profile test build backend-test >&2
	@start=$$(date +%s); \
	result=$$($(COMPOSE) -p lo-mutation-baseline --profile test run --rm -T -e MUTATION_LINES=all backend-test sh tests/mutation/run.sh); \
	end=$$(date +%s); \
	printf '%s\n' "$$result"; \
	total=$$(printf '%s' "$$result" | jq -r .total); \
	killed=$$(printf '%s' "$$result" | jq -r .killed); \
	score=$$(printf '%s' "$$result" | jq -r .score); \
	printf 'mutation-baseline: %s/%s killed, score=%s, %ss wall time\n' "$$killed" "$$total" "$$score" "$$((end - start))" >&2

.PHONY: release
release: ## Deploy CANARY_VERSION and run the controller through staging, 5%, 25% (docs/adr/0013 §4)
	@sh app/load.sh & \
	load_pid=$$!; \
	CANARY_VERSION="$(CANARY_VERSION)" STAGE_SECONDS="$(STAGE_SECONDS)" sh core/launchpad.sh; \
	rc=$$?; \
	kill "$$load_pid" 2>/dev/null || true; \
	wait "$$load_pid" 2>/dev/null || true; \
	exit "$$rc"

.PHONY: demo-rollback
demo-rollback: ## Release the failing default and prove the canary rolls back on its own (docs/adr/0013 §4)
	@stable=$$(curl -fsS --connect-timeout 1 --max-time 3 "$(APP_URL)/healthz" | jq -r .version); \
	printf '[demo-rollback] stable is %s; releasing %s (waitlist targeted on)\n' "$$stable" "$(CANARY_VERSION)" >&2; \
	if $(MAKE) --no-print-directory release CANARY_VERSION=$(CANARY_VERSION); then \
		printf 'NO-GO: demo-rollback — release passed; expected a NO-GO at 5%%\n'; \
		exit 1; \
	fi; \
	canary_w=$$(curl -fsS --connect-timeout 1 --max-time 3 "$(ENVOY_ADMIN_URL)/runtime" | jq -r '.entries["weights.canary"].final_value // "none"'); \
	if [ "$$canary_w" != "0" ]; then \
		printf 'NO-GO: demo-rollback — Envoy still reports weights.canary=%s after rollback\n' "$$canary_w"; \
		exit 1; \
	fi; \
	ok=0; total=10; i=0; \
	while [ "$$i" -lt "$$total" ]; do \
		v=$$(curl -fsS --connect-timeout 1 --max-time 3 "$(APP_URL)/healthz" | jq -r .version); \
		[ "$$v" = "$$stable" ] && ok=$$((ok + 1)); \
		i=$$((i + 1)); \
	done; \
	if [ "$$ok" -ne "$$total" ]; then \
		printf 'NO-GO: demo-rollback — only %s/%s healthz through Envoy report the stable version\n' "$$ok" "$$total"; \
		exit 1; \
	fi; \
	printf 'GO: demo-rollback\n'

.PHONY: demo-hold
demo-hold: ## Same release, kill switch on: verify GO end to end, canary held at 25% for the human gate (docs/adr/0014)
	@backup=$$(mktemp); \
	cp app/flags/flags.json "$$backup"; \
	trap 'cat "$$backup" > app/flags/flags.json; rm -f "$$backup"' EXIT INT TERM; \
	$(MAKE) --no-print-directory kill-switch; \
	stable=$$(curl -fsS --connect-timeout 1 --max-time 3 "$(APP_URL)/healthz" | jq -r .version); \
	printf '[demo-hold] stable is %s; releasing %s with waitlist off\n' "$$stable" "$(CANARY_VERSION)" >&2; \
	if ! $(MAKE) --no-print-directory release CANARY_VERSION=$(CANARY_VERSION); then \
		printf 'NO-GO: demo-hold — release rolled back; expected GO through 25%%\n'; \
		exit 1; \
	fi; \
	canary_w=$$(curl -fsS --connect-timeout 1 --max-time 3 "$(ENVOY_ADMIN_URL)/runtime" | jq -r '.entries["weights.canary"].final_value // "none"'); \
	if [ "$$canary_w" != "25" ]; then \
		printf 'NO-GO: demo-hold — Envoy reports weights.canary=%s, want 25\n' "$$canary_w"; \
		exit 1; \
	fi; \
	seen_canary=0; seen_stable=0; total=40; i=0; \
	while [ "$$i" -lt "$$total" ]; do \
		v=$$(curl -fsS --connect-timeout 1 --max-time 3 "$(APP_URL)/healthz" | jq -r .version); \
		[ "$$v" = "$(CANARY_VERSION)" ] && seen_canary=1; \
		[ "$$v" = "$$stable" ] && seen_stable=1; \
		i=$$((i + 1)); \
	done; \
	if [ "$$seen_canary" -ne 1 ] || [ "$$seen_stable" -ne 1 ]; then \
		printf 'NO-GO: demo-hold — %s healthz samples through Envoy did not see both versions (canary seen=%s, stable seen=%s)\n' "$$total" "$$seen_canary" "$$seen_stable"; \
		exit 1; \
	fi; \
	sh adapters/$(DELIVERY)/rollback.sh; \
	printf '[demo-hold] cleanup: rollback to 100/0 (not a verdict — the controller held at 25%%, this is hygiene for the next run)\n' >&2; \
	printf 'GO: demo-hold\n'

# Every target below writes app/flags/flags.json in place (jq's output
# captured in a shell variable, then `>` truncates and rewrites the same
# path) and never via a temp-file-plus-rename, even a same-directory one.
# Reproduced live 2026-09-14 on flagd v0.16.3: a workbench container and the
# flagd container each bind-mount app/flags/ separately (docs/adr/0012 §2);
# a `mv`/`rename(2)` onto the watched path — same filesystem or not — gives
# the path a new inode, and flagd's fileinfo poller, seen from the *other*
# container's mount of the same host directory, would intermittently keep
# serving the pre-rename (stale) evaluation, sometimes for minutes, with no
# error and no further log line — the file on disk and `git diff` were
# already correct while `waitlist` kept evaluating as if they were not. An
# in-place truncate+write (no rename, same inode throughout) reproduced
# correctly every time in the same setup; that is the only reason this
# repo does not use the usual write-temp-then-rename pattern here.
.PHONY: kill-switch
kill-switch: ## Turn `waitlist` off for every version, live within seconds, no deploy (docs/adr/0013 §6)
	@content=$$(jq 'del(.flags.waitlist.targeting) | .flags.waitlist.defaultVariant = "off"' app/flags/flags.json) \
		&& printf '%s\n' "$$content" > app/flags/flags.json; \
	i=0; v=""; \
	while [ "$$i" -lt "$(READY_TIMEOUT)" ]; do \
		v=$$(curl -fsS --connect-timeout 1 --max-time 3 -H 'Content-Type: application/json' \
			-d '{"context":{"version":"$(CANARY_VERSION)"}}' \
			"http://$(PLANE_HOST):8016/ofrep/v1/evaluate/flags/waitlist" | jq -r .value 2>/dev/null) || v=""; \
		[ "$$v" = "false" ] && break; \
		i=$$((i + 1)); sleep 1; \
	done; \
	if [ "$$v" != "false" ]; then \
		printf 'NO-GO: kill-switch — waitlist still evaluates %s for %s after %ss\n' "$${v:-no answer}" "$(CANARY_VERSION)" "$(READY_TIMEOUT)"; \
		exit 1; \
	fi; \
	printf 'lights-out: waitlist is off for every version (app/flags/flags.json edited; git checkout it to undo)\n' >&2; \
	printf 'GO: kill-switch\n'

.PHONY: freeze
freeze: ## Turn release-freeze on: launchpad refuses to deploy or shift (docs/adr/0013 §6)
	@content=$$(jq '.flags["release-freeze"].defaultVariant = "on"' app/flags/flags.json) \
		&& printf '%s\n' "$$content" > app/flags/flags.json; \
	printf 'lights-out: release-freeze is on (app/flags/flags.json edited; git checkout it to undo)\n' >&2; \
	printf 'GO: freeze\n'

.PHONY: unfreeze
unfreeze: ## Turn release-freeze off (docs/adr/0013 §6)
	@content=$$(jq '.flags["release-freeze"].defaultVariant = "off"' app/flags/flags.json) \
		&& printf '%s\n' "$$content" > app/flags/flags.json; \
	printf 'lights-out: release-freeze is off\n' >&2; \
	printf 'GO: unfreeze\n'

# The M6 acceptance command (docs/adr/0019 §7). A replay on a per-`up`
# plane: the ticket's document is deleted first so the machine starts at
# `opened` every time — a production tower never deletes. Then: open
# (document + the `assign` event), the inproc orchestrator until the
# queue is empty, the final state asserted as rolled-back (the done-when
# ends in a rollback; the demo-rollback precedent), and the audit. Order
# inside `demo`: after demo-rollback, so ≥ 97 s pass between its rollback
# and this canary's 5% verify and the 1m window (docs/adr/0013 §2) holds
# only this stage's canary; put e2e first and the two runs share a window.
TICKET ?= 0001

.PHONY: e2e
e2e: ## Golden path at L0: ticket → PR → CI → merge → canary → verify NO-GO → rollback, audited (docs/adr/0019)
	@$(MAKE) --no-print-directory up
	@printf '[e2e] replay: deleting the document of ticket %s before opening it again\n' "$(TICKET)" >&2
	@sh adapters/$(STATE_STORE)/delete.sh tickets "$(TICKET)" || { printf 'NO-GO: e2e — could not reset the document\n'; exit 1; }
	@sh core/tower.sh open "$(TICKET)" || { printf 'NO-GO: e2e — could not open ticket %s\n' "$(TICKET)"; exit 1; }
	@sh adapters/$(ORCHESTRATOR)/run.sh || { printf 'NO-GO: e2e — a step failed; see the [tower] lines above\n'; exit 1; }
	@state=$$(sh adapters/$(STATE_STORE)/get.sh tickets "$(TICKET)" | jq -r .state); \
	if [ "$$state" != "rolled-back" ]; then \
		printf 'NO-GO: e2e — ticket %s ended at %s, expected rolled-back\n' "$(TICKET)" "$$state"; exit 1; \
	fi
	@$(MAKE) --no-print-directory audit TICKET="$(TICKET)" >&2 || { printf 'NO-GO: e2e — audit did not pass\n'; exit 1; }
	@printf 'GO: e2e\n'

.PHONY: audit
audit: ## Rebuild the chain deploy → merge → PR → ticket → spec from the state store and the code host: TICKET=<id> (docs/adr/0019 §6)
	@TICKET="$(TICKET)" sh core/audit.sh
