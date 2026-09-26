"""Diagnostic model adapters (lazy optional dependencies).

Nothing here imports torch, Chronos, TimesFM, or TabPFN at module
load; each adapter imports its backend inside methods/probes only.
"""

__all__: list = []
