# workloads/minimal-js

The second stack (docs/adr/0042 §9): a javascript repository the gates run
on with no plane. Laid out as a repository of its own would be: code in
`src/`, tests on node's own runner in `test/`, the lights-out contract in
`.lights-out/`, the gates half only (`workload.env`, `worker.md`,
`policy.env`, `runners/`): no compose fragment, no flag file, nothing to
release. `./go demo-init` copies this directory into a fresh git repository
outside the checkout, attaches it, runs the gates on the contract as
committed (Stryker and eslint inside the node image it names), then
`./go init` and the gates again on the draft, in the workbench, with no
engine. `.lights-out/runners/` is byte for byte `stacks/javascript/runners/`,
which `./go init` copies; `ci/init.sh` keeps the two equal.
