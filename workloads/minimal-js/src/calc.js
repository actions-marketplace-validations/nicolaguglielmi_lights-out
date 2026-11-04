// SPDX-License-Identifier: Apache-2.0
//
// A few functions with branches worth mutating (docs/adr/0042 §9): small
// enough for a whole-scope mutation run in seconds, with tests that kill
// every mutant but the two equivalent ones below, so the measured
// baseline (0.9375, .lights-out/workload.env) is a real bar.

export function add(a, b) {
  return a + b;
}

// The two boundary comparisons have equivalent mutants (`<` to `<=`
// returns `low` for `value === low` either way, and the same at `high`):
// no test can kill them, and the measured baseline says so.
export function clamp(value, low, high) {
  if (low > high) {
    throw new RangeError(`low ${low} is above high ${high}`);
  }
  if (value < low) {
    return low;
  }
  if (value > high) {
    return high;
  }
  return value;
}

export function isEven(n) {
  return n % 2 === 0;
}

export function mean(values) {
  if (values.length === 0) {
    return null;
  }
  let total = 0;
  for (const v of values) {
    total += v;
  }
  return total / values.length;
}
