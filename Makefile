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
CI_CHECKS := secrets lint shell help readme gitea-compat profiles compose contract

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
	@printf '[demo] e2e: NOT YET (M6)\n' >&2
	@printf 'lights-out: app at %s, Gitea at http://localhost:3000, Prometheus at http://localhost:9090\n' "$(APP_URL)" >&2
	@now=$$(date +%s); t0=$${LIGHTS_OUT_T0:-$$now}; elapsed=$$((now - t0)); \
	if [ "$(DEMO_BUDGET_SECONDS)" -gt 0 ] && [ "$$elapsed" -gt "$(DEMO_BUDGET_SECONDS)" ]; then \
		printf 'NO-GO: demo — rollback reached, but %ss > %ss budget (plan §2)\n' "$$elapsed" "$(DEMO_BUDGET_SECONDS)"; \
		exit 1; \
	fi; \
	printf 'GO: demo, milestone M3, %ss to rollback (budget %ss, plan §2)\n' "$$elapsed" "$(DEMO_BUDGET_SECONDS)"

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

.PHONY: e2e
e2e: ## Golden path: ticket, PR, CI, canary, rollback
	$(call not_yet,e2e,M6)
