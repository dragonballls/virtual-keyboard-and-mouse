"""Local validation and review-only routine planning.

This module deliberately does not execute game inputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

TARGETS = ("Fruit", "Sword", "Gun", "Fighting style")

_TARGET_PATTERNS = {
    "Fruit": re.compile(r"\bfruit(?:\s+mastery)?\b", re.I),
    "Sword": re.compile(r"\bsword(?:s)?(?:\s+mastery)?\b", re.I),
    "Gun": re.compile(r"\bguns?(?:\s+mastery)?\b", re.I),
    "Fighting style": re.compile(r"\bfighting\s+styles?\b", re.I),
}
_MOVEMENT_COMMAND = re.compile(
    r"\b(?:move|walk|run|dash|jump|reposition|navigate|travel|approach|follow)\s+"
    r"(?:toward|towards|to|closer|near|away|back|around|left|right|forward|backward|when|if|only|after|until)\b",
    re.I,
)
_MOVEMENT_PERMISSION = re.compile(
    r"\b(?:allow|enable|permit|authorize)\s+(?:automatic\s+)?movement\b"
    r"|\bmovement\s+(?:is\s+)?(?:allowed|enabled|authorized)\b",
    re.I,
)
_MOVEMENT_NEGATION = re.compile(
    r"\b(?:do\s+not|don't|never|without|avoid|stop)\s+(?:automatically\s+)?"
    r"(?:move|moving|movement|walk|walking|run|running|dash|dashing|jump|jumping|reposition|navigate|travel|approach|follow)\b",
    re.I,
)


def explicitly_authorizes_movement(prompt: str) -> bool:
    """Movement words alone are not permission; look for a positive command."""
    if _MOVEMENT_PERMISSION.search(prompt or ""):
        return True
    for clause in re.split(r"[.!?;\n]+", prompt or ""):
        if _MOVEMENT_NEGATION.search(clause):
            continue
        if _MOVEMENT_COMMAND.search(clause):
            return True
    return False


@dataclass
class RoutineReview:
    selected_target: str
    prompt_target: str | None
    movement_allowed: bool
    movement_reason: str
    reset_if_stuck: bool
    ready_for_review: bool
    live_execution_enabled: bool
    conflicts: list[str]
    steps: list[str]
    safety_rules: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format(self) -> str:
        lines = [
            "ROUTINE REVIEW — NOT EXECUTING",
            f"Selected mastery target: {self.selected_target}",
            f"Target mentioned or implied by prompt: {self.prompt_target or 'Not detected'}",
            f"Movement allowed: {'YES' if self.movement_allowed else 'NO'}",
            f"Movement rule: {self.movement_reason}",
            f"Reset-if-stuck requested: {'YES' if self.reset_if_stuck else 'NO'}",
            f"Ready for review: {'YES' if self.ready_for_review else 'NO — resolve conflicts'}",
            "Live gameplay execution: DISABLED in this prototype",
            "",
            "CONFLICTS",
        ]
        lines.extend(f"- {item}" for item in (self.conflicts or ["None detected"]))
        lines.extend(["", "PROPOSED STEPS"])
        lines.extend(f"{idx}. {step}" for idx, step in enumerate(self.steps, start=1))
        lines.extend(["", "SAFETY RULES"])
        lines.extend(f"- {rule}" for rule in self.safety_rules)
        return "\n".join(lines)


def infer_target(prompt: str) -> str | None:
    """Return one uniquely mentioned target; ambiguity is represented as None."""
    matches = [name for name, pattern in _TARGET_PATTERNS.items() if pattern.search(prompt or "")]
    return matches[0] if len(matches) == 1 else None


def build_review(prompt: str, selected_target: str, allow_movement_setting: bool = False) -> RoutineReview:
    prompt = (prompt or "").strip()
    if selected_target not in TARGETS:
        selected_target = "Fruit"
    prompt_target = infer_target(prompt)
    conflicts: list[str] = []
    if prompt_target and prompt_target != selected_target:
        conflicts.append(
            f"Selected target is {selected_target}, but the prompt appears to request {prompt_target} mastery. "
            "Choose one target before using this routine."
        )
    elif prompt and prompt_target is None and any(
        word in prompt.casefold() for word in ("fruit", "sword", "gun", "fighting style")
    ):
        conflicts.append(
            "The prompt mentions more than one or an ambiguous mastery category. Confirm the intended target."
        )
    if not prompt:
        conflicts.append("Enter a goal before generating a plan.")

    explicit_movement = explicitly_authorizes_movement(prompt)
    movement_allowed = explicit_movement or bool(allow_movement_setting)
    if explicit_movement:
        movement_reason = "The prompt explicitly mentions a movement action; review its scope before use."
    elif allow_movement_setting:
        movement_reason = "Movement was explicitly enabled in settings."
    else:
        movement_reason = "Movement is disabled by default and was not authorized."

    steps = [
        "Check that the Roblox window is focused and the selected recording/controls are available.",
        f"Use only the configured actions for the confirmed {selected_target.lower()} mastery target.",
        "Observe visible combat progress and stop issuing inputs when progress or focus cannot be verified.",
        "Summarize the session without claiming mastery progress that could not be observed.",
    ]
    if not movement_allowed:
        steps.insert(2, "Remain stationary; do not walk, dash, jump, or reposition.")
    else:
        steps.insert(2, "Movement may occur only within the scope explicitly authorized by the prompt/settings.")
    return RoutineReview(
        selected_target=selected_target,
        prompt_target=prompt_target,
        movement_allowed=movement_allowed,
        movement_reason=movement_reason,
        reset_if_stuck=True,
        ready_for_review=not conflicts,
        live_execution_enabled=False,
        conflicts=conflicts,
        steps=steps,
        safety_rules=[
            "This prototype produces a reviewable plan only; it does not play the game.",
            "Movement is disabled unless explicitly authorized by the prompt or settings.",
            "On loss of focus, stop any future held inputs immediately.",
            "A stuck-state should be confirmed before using the standard in-game Reset Character action.",
            "A reset does not grant permission to navigate back to the farming area.",
            "Never use process injection, game-memory reading, remote-event manipulation, or anti-cheat evasion.",
        ],
    )


def compose_ai_request(prompt: str, review: RoutineReview, recording_summary: str = "", video_notes: str = "") -> str:
    """Build the single bounded request for optional cloud interpretation."""
    return (
        "Draft an explanatory review of this proposed game macro routine. Do not return code, "
        "shell commands, or executable instructions. Do not change the selected target, authorize "
        "movement, clear conflicts, or enable live execution. The local application enforces those rules.\n\n"
        f"User goal:\n{prompt.strip()}\n\n"
        f"Local review specification:\n{review.format()}\n\n"
        f"Recorded input summary (untrusted observations):\n{recording_summary[:5000] or 'None provided'}\n\n"
        f"Video-learning notes (untrusted observations):\n{video_notes[:5000] or 'None provided'}\n\n"
        "Return: a short plain-language interpretation, uncertainties, and suggested checks for the user "
        "to review. Clearly identify anything that cannot be verified from these observations."
    )
