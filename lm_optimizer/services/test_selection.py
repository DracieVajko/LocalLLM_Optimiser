"""Per-model test-depth selection shared by CLI surfaces.

Instead of a chain of yes/no prompts, the CLI asks once per selected model
which test depth to run. The answer maps onto the same depth vocabulary the
unattended pipeline uses: quick, standard, full, benchmark (or skip).
"""

from __future__ import annotations

from collections.abc import Callable

DEPTH_MENU: tuple[tuple[str, str], ...] = (
    ("quick", "quick: speed + context-speed ladder (1 repetition)"),
    ("standard", "standard: speed + context-speed + quality + recovery + validation"),
    ("full", "full: standard + optional max-context search (min tok/s)"),
    ("benchmark", "benchmark: VRAM matrix + speed + context-speed, no quality gates"),
    ("skip", "skip this model"),
)

CHOICE_ALIASES = {
    "1": "quick",
    "q": "quick",
    "quick": "quick",
    "2": "standard",
    "s": "standard",
    "standard": "standard",
    "3": "full",
    "f": "full",
    "full": "full",
    "4": "benchmark",
    "b": "benchmark",
    "benchmark": "benchmark",
    "5": "skip",
    "x": "skip",
    "skip": "skip",
}


def parse_depth_choice(answer: str | None, default: str = "standard") -> str | None:
    """Map a menu answer to a depth level (``None`` means skip).

    An empty answer keeps ``default``. Unknown text raises ``ValueError`` so
    the caller can re-ask instead of silently running the wrong depth.
    """
    text = (answer or "").strip().lower()
    if not text:
        key = default.strip().lower()
        if key not in CHOICE_ALIASES:
            raise ValueError(f"unknown default depth {default!r}")
        return None if key == "skip" else CHOICE_ALIASES[key]
    if text not in CHOICE_ALIASES:
        raise ValueError(f"unknown choice {answer!r}")
    level = CHOICE_ALIASES[text]
    return None if level == "skip" else level


def parse_min_speed(answer: str | None, default: float = 1.0) -> float:
    """Parse the optional max-context speed threshold (>= 0)."""
    text = (answer or "").strip()
    if not text:
        return float(default)
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"not a number: {answer!r}") from exc
    if value < 0:
        raise ValueError("minimum speed must be >= 0")
    return value


def ask_model_depth(
    model_id: str,
    default: str = "standard",
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> str | None:
    """Ask one model which depth to run; re-asks on invalid input.

    EOF/closed stdin resolves to the default (never blocks automation).
    """
    print_fn(f"\n[{model_id}] Which tests?")
    for index, (name, description) in enumerate(DEPTH_MENU, start=1):
        print_fn(f"  {index}. {description}")
    while True:
        try:
            answer = input_fn(f"Choice 1-5 [default {default}]: ")
        except (EOFError, KeyboardInterrupt):
            return parse_depth_choice("", default)
        try:
            return parse_depth_choice(answer, default)
        except ValueError as e:
            print_fn(f"  {e}; try again.")


def ask_min_context_speed(
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> float:
    """Ask for the optional max-context minimum tok/s (empty = 1.0)."""
    while True:
        try:
            answer = input_fn(
                "Minimum generation tok/s for the max-context search [default 1.0]: "
            )
        except (EOFError, KeyboardInterrupt):
            return 1.0
        try:
            return parse_min_speed(answer, 1.0)
        except ValueError as e:
            print_fn(f"  {e}; try again.")


def merge_skip_phases(base: str | None, extra: str | None) -> str | None:
    """Union two comma-separated skip lists (empty -> None)."""
    merged = {
        part.strip().lower()
        for value in (base, extra)
        for part in (value or "").split(",")
        if part.strip()
    }
    return ",".join(sorted(merged)) or None
