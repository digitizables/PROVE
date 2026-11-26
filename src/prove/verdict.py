"""Map an adapter playtest record onto a PROVE verdict.

The rules live in docs/integration/roblox-studio-adapter.md.
"""

from __future__ import annotations


def verdict_from_studio(studio: dict) -> str:
    console = studio.get("console") or {}
    if console.get("reset"):
        return "inconclusive"
    passed = studio.get("passed")
    if passed is True:
        return "pass"
    if passed is False:
        return "fail"
    return "inconclusive"
