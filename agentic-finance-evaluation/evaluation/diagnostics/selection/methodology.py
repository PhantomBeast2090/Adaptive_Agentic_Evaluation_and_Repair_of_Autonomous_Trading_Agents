"""Selection methodology constants for adaptive-discrimination v1 (E2-D).

This module is the single authoritative statement of the deterministic
lexicographic selection policy. Everything here is a named, versioned
constant; there is no hidden state, no randomness, no wall-clock use.

Method identity: ``adaptive-discrimination``, version ``v1``.

Policy summary
--------------
For each eligible candidate test T, with O the current open-hypothesis
set (statuses PROPOSED/UNRESOLVED/WEAKENED, reused from E2-C):

* ``D(T)`` — rival discrimination: number of unordered open-hypothesis
  pairs whose committed predictions for T carry different
  ``expected_direction`` values. A pure integer count; never converted
  into a probability, information gain, or utility.
* ``C(T)`` — open-hypothesis coverage: number of distinct open
  hypotheses with a committed prediction for T. Confidence values play
  no role: confidence is state metadata, not a ranking mechanism.
* ``cost(T)`` — the test's own ``estimated_cost`` as defined by the
  frozen E0 contract. Preferred lower only after D and C tie.
* ``test_id`` — final tie-break, purely for reproducibility.

Selection key: ``(-D, -C, cost, test_id)``; the first candidate in this
ordering is the preferred candidate. It is described as "preferred under
adaptive-discrimination v1" — never optimal, best, or most informative.

Fallback: when no eligible candidate has D(T) > 0, the same key still
decides (coverage, then cost, then id), and the rationale states
explicitly that no directional rival separation was available. No
discrimination is fabricated.
"""

from __future__ import annotations

METHOD = "adaptive-discrimination"
VERSION = "v1"

# Rationale sentence templates (structured facts only, no LLM prose).
NO_SEPARATION_PREFIX = (
    "no candidate provided directional rival separation; "
)
DISCRIMINATION_TEMPLATE = (
    "{pairs} rival hypothesis pairs separated by expected directions; "
    "{coverage} open hypotheses covered; estimated cost={cost}."
)
