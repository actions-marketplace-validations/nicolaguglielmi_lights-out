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
	@printf '[demo] ci (M0): running\n'
	@$(MAKE) --no-print-directory ci
	@printf '[demo] engine-compat: NOT YET (M2)\n' >&2
	@printf '[demo] up: NOT YET (M2)\n' >&2
	@printf '[demo] deploy: NOT YET (M3)\n' >&2
	@printf '[demo] verify: NOT YET (M3)\n' >&2
	@printf '[demo] rollback: NOT YET (M3)\n' >&2
	@printf '[demo] e2e: NOT YET (M6)\n' >&2
	@printf 'GO: demo, milestone M0. Green means the repo is coherent, not that the platform works yet.\n'

.PHONY: up
up: ## Start the local plane in compose
	$(call not_yet,up,M2)

.PHONY: down
down: ## Stop the local plane
	$(call not_yet,down,M2)

.PHONY: demo-rollback
demo-rollback: ## Release a failing version and watch the canary roll back
	$(call not_yet,demo-rollback,M3)

.PHONY: e2e
e2e: ## Golden path: ticket, PR, CI, canary, rollback
	$(call not_yet,e2e,M6)
