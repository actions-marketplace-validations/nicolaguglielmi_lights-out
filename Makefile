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
# alias (docs/adr/0011); it is the one place the hostname is written.
APP_URL ?= http://host.containers.internal:8080

# Milestone stubs. A target whose milestone has not arrived fails loudly.
define not_yet
	@printf 'NO-GO: %s arrives with %s. Nothing runs yet.\n' "$(1)" "$(2)" >&2; exit 1
endef

.PHONY: help
help: ## List the targets
	@printf 'lights-out  (profile: %s)\n\n' "$(PROFILE)"
	@awk 'BEGIN{FS=":.*## "} /^[a-z][a-z0-9-]*:.*## /{printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@for c in $(CI_CHECKS); do printf '  %-16s %s\n' "ci-$$c" "one self-check, see ci/$$c.sh"; done
	@printf '  %-16s %s\n' ci-engine-compat "host-side engine check, ci/engine-compat.sh (joins ci at M2)"
	@printf '\n  Host side, via ./go only:\n  %-16s %s\n  %-16s %s\n' shell "interactive shell inside workbench" clean "remove the workbench image"

# Self-checks run by `ci`, in order. engine-compat runs on the host (ADR 0004) and joins at M2.
CI_CHECKS := secrets lint shell help readme gitea-compat profiles contract

.PHONY: ci
ci: $(addprefix ci-,$(CI_CHECKS)) ## Repo self-checks (ADR 0002), same on laptop and CI
	@printf 'GO: ci\n'

.PHONY: ci-%
ci-%:
	@sh ci/$*.sh

.PHONY: demo
demo: ## The demo, as far as the current milestone takes it (ADR 0003)
	@printf '[demo] ci (M1): running\n'
	@$(MAKE) --no-print-directory ci
	@printf '[demo] engine-compat: NOT YET (M2)\n' >&2
	@$(MAKE) --no-print-directory up
	@printf '[demo] up: app only, plane at M2\n' >&2
	@curl -fsS --connect-timeout 1 --max-time 3 "$(APP_URL)/healthz" >/dev/null \
		|| { printf 'NO-GO: demo — smoke check failed at %s/healthz\n' "$(APP_URL)"; exit 1; }
	@printf '[demo] smoke: %s/healthz ok\n' "$(APP_URL)" >&2
	@$(MAKE) --no-print-directory verify
	@printf '[demo] verify: metric shape only, evaluation at M3\n' >&2
	@printf '[demo] deploy: NOT YET (M3)\n' >&2
	@printf '[demo] rollback: NOT YET (M3)\n' >&2
	@printf '[demo] e2e: NOT YET (M6)\n' >&2
	@printf 'lights-out: app running at %s\n' "$(APP_URL)" >&2
	@printf 'GO: demo, milestone M1. Green means the repo is coherent and the app answers; canary and rollback are not real yet.\n'

.PHONY: up
up: ## Start the app in compose (M1: app only, the rest of the plane arrives at M2)
	@$(COMPOSE) up -d --build postgres migrate geocoder backend
	@printf 'lights-out: waiting for %s/healthz\n' "$(APP_URL)" >&2
	@i=0; \
	while ! curl -fsS --connect-timeout 1 --max-time 3 "$(APP_URL)/healthz" >/dev/null 2>&1; do \
		i=$$((i + 1)); \
		if [ "$$i" -ge 60 ]; then \
			printf 'lights-out: backend did not answer /healthz within 60s\n' >&2; \
			exit 1; \
		fi; \
		sleep 1; \
	done
	@printf 'lights-out: app is up at %s\n' "$(APP_URL)" >&2

.PHONY: down
down: ## Stop the app
	@$(COMPOSE) --profile test down

.PHONY: test
test: ## Run the backend test suite against compose Postgres (docs/adr/0010)
	$(COMPOSE) --profile test run --rm --build backend-test

.PHONY: verify
verify: ## Check verify/slo.promql against the live app (M1: metric shape only, evaluated at M3)
	@APP_URL="$(APP_URL)" sh verify/metric-shape.sh

.PHONY: demo-rollback
demo-rollback: ## Release a failing version and watch the canary roll back
	$(call not_yet,demo-rollback,M3)

.PHONY: e2e
e2e: ## Golden path: ticket, PR, CI, canary, rollback
	$(call not_yet,e2e,M6)
