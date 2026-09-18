"""Directional-band comparison methodology, version 1 (E2-C).

This module is the single authoritative statement of how a committed
directional prediction is adjudicated against an observed diagnostic
measurement. Everything here is a named, versioned constant plus pure
functions; there is no hidden state, no randomness, no wall-clock use.

Method identity: ``directional-band``, version ``v1``.

Rule summary
------------
Let ``obs`` be the observed diagnostic value and ``base`` the baseline
control value for the same metric.

* Either side missing or explicitly undefined → ``INCONCLUSIVE`` with the
  recorded reason. The method never pretends to distinguish what the
  evidence cannot distinguish.
* ``base == 0``: exact zero comparisons (counts and rates at exact zero
  are exact — no epsilon is invented where zero is meaningful).
  ``INCREASE`` iff ``obs > 0``; ``DECREASE`` iff ``obs < 0``;
  ``NO_CHANGE`` iff ``obs == 0``.
* ``base != 0``: relative materiality band ``TAU = 0.01`` on the
  relative change ``r = (obs - base) / |base|``. Moves within ±1% are
  treated as indistinguishable from session-grain measurement noise, so
  ``NO_CHANGE`` is attainable and directional claims must clear the band
  to count: ``INCREASE`` iff ``r > TAU``; ``DECREASE`` iff ``r < -TAU``;
  ``NO_CHANGE`` iff ``|r| <= TAU``. The ``|base|`` denominator keeps the
  rule sign-correct for negative controls.
* A directional prediction whose observation falls outside its claimed
  region (including inside the band) is ``CONTRADICTS``: a directional
  claim that fails to materialise is evidence against the mechanism,
  not an absence of evidence.

Confidence transition (bounded, symmetric, least-claim):
``SUPPORTS +0.10``, ``CONTRADICTS -0.10``, ``INCONCLUSIVE 0.0``,
clamped to ``[0, 1]``. These steps are methodological conventions,
documented here and stamped on every update — not probabilities,
likelihoods, priors, or posteriors. No Bayesian vocabulary appears
anywhere in this package (enforced by test).

Lifecycle transitions (conservative ladder; single observations never
jump to endorsement or rejection):
``INCONCLUSIVE`` preserves status; ``SUPPORTS``: PROPOSED→UNRESOLVED,
UNRESOLVED→SUPPORTED, WEAKENED→UNRESOLVED, SUPPORTED→SUPPORTED;
``CONTRADICTS``: PROPOSED/UNRESOLVED/SUPPORTED→WEAKENED,
WEAKENED→REJECTED; ``REJECTED`` is terminal under every outcome.
"""

from __future__ import annotations

METHOD = "directional-band"
VERSION = "v1"

# Minimum relative move counted as a directional change.
TAU = 0.01

# Bounded symmetric confidence steps per compatibility outcome.
CONFIDENCE_STEP_SUPPORTS = 0.10
CONFIDENCE_STEP_CONTRADICTS = -0.10
CONFIDENCE_STEP_INCONCLUSIVE = 0.0

# Statuses still admitting rival explanations ("open" hypotheses).
OPEN_STATUSES = ("PROPOSED", "UNRESOLVED", "WEAKENED")
