"""E4-F accumulation episode wiring (new, E4-owned).

Frozen Tier-1 modules are only called, never modified. No success,
superiority, learning, or self-repair claims are made here.
"""

from experiments.e4f.episode_driver import run_r_branch

__all__ = ["run_r_branch"]
