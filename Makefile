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
demo: ## The demo, as far as the current milestone takes it (ADR 0003)
	@printf '[demo] engine-compat: done on the host by ./go before this run\n' >&2
	@printf '[demo] ci (M2): running\n'
	@$(MAKE) --no-print-directory ci
	@$(MAKE) --no-print-directory up
	@printf '[demo] up: L0 plane, %s\n' "$(PLANE_ADAPTERS)" >&2
	@$(MAKE) --no-print-directory smoke
	@printf '[demo] smoke: a meetup created through Envoy at %s\n' "$(APP_URL)" >&2
	@$(MAKE) --no-print-directory verify
	@printf '[demo] verify: metric shape only, evaluation at M3\n' >&2
	@printf '[demo] deploy: NOT YET (M3)\n' >&2
	@printf '[demo] rollback: NOT YET (M3)\n' >&2
	@printf '[demo] e2e: NOT YET (M6)\n' >&2
	@printf 'lights-out: app at %s, Gitea at http://localhost:3000, Prometheus at http://localhost:9090\n' "$(APP_URL)" >&2
	@printf 'GO: demo, milestone M2. Green means the repo is coherent and the L0 plane answers; canary and rollback are not real yet.\n'

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
