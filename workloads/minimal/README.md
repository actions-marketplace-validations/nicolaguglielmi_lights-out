# workloads/minimal

Exists to prove the seam is real, not to be a second app (docs/adr/0030).
It is laid out as a repository of its own would be: code at the root, the
lights-out contract in `.lights-out/` (docs/adr/0036). `./go demo-seam`
copies this directory into a fresh git repository outside the checkout and
attaches it, the way you attach yours; nothing selects it in place.
