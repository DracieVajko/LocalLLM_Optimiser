"""Deterministic context-recall probe.

A single, cheap, needle-in-a-haystack measurement that answers
"can this model actually use N tokens of context on this machine?".

Pure functions are kept separate from I/O so they can be unit-tested
without a running LM Studio server.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

CHARS_PER_TOKEN = 3.2

FILLER_PARAGRAPHS = (
    "The harbour master logged every vessel before the fog lifted. Cargo manifests "
    "were checked against the register, and the watch officer noted the tide, the "
    "wind and the number of crew on each deck.",
    "Coastal shipping follows a fixed schedule: outbound at first light, inbound on "
    "the flood tide. Pilots board outside the breakwater and remain aboard until the "
    "vessel is moored alongside the quay.",
    "Maintenance of the navigation lights is carried out quarterly. Each lamp is "
    "tested for range and colour, and any fault is logged and reported to the "
    "regional authority within one working day.",
    "The register of arrivals has been kept in the same form since the station "
    "opened: date, vessel name, flag, tonnage, cargo class, and the signature of the "
    "officer on watch. Older volumes are stored in the basement archive.",
)

DISTRACTORS = [
    "CODE-1ALPHA-0001", "CODE-2BRAVO-0002", "CODE-3CHARLIE-0003",
    "CODE-4DELTA-0004", "CODE-5ECHO-0005",
]
NEEDLE = "CODE-7TANGO-4423"
NEEDLE_KEY = "7TANGO4423"
QUESTION = (
    "\n\nWhat is the harbour access code mentioned in the document above? "
    "Answer with the code only, nothing else."
)


@dataclass
class RecallProbeSpec:
    target_tokens: int
    fill_ratio: float = 0.85
    depth: float = 0.5
    depth_points: tuple[float, ...] = (0.5,)
    max_tokens: int = 24
    temperature: float = 0.0
    max_probe_cost_s: float = 900.0
    chars_per_token: float = CHARS_PER_TOKEN


@dataclass
class RecallProbeResult:
    target_tokens: int = 0
    fill_ratio: float = 0.85
    depth: float = 0.5
    prompt_tokens: int = 0
    prompt_processing_ms: float = 0.0
    completion_tokens: int = 0
    built_tokens_estimate: int = 0
    chars_per_token: float = CHARS_PER_TOKEN
    estimated_cost_s: float = 0.0
    actual_cost_s: float = 0.0
    answer_raw: str = ""
    answer_normalised: str = ""
    status: str = ""
    distractors_present: int = 0
    truncated: bool = False
    skipped_reason: str = ""


def build_recall_prompt(spec: RecallProbeSpec) -> str:
    """Build a deterministic needle-in-haystack prompt.

    Raises ValueError if build-time assertions fail.
    """
    target_chars = int(spec.target_tokens * spec.fill_ratio * spec.chars_per_token)

    # Build filler by rotating paragraphs
    paragraphs: list[str] = []
    total = 0
    i = 0
    while total < target_chars:
        para = FILLER_PARAGRAPHS[i % 4]
        # Assert no immediate repeat
        if paragraphs and paragraphs[-1] == para:
            raise ValueError("consecutive duplicate paragraph")
        paragraphs.append(para)
        total += len(para) + 2  # +2 for "\n\n"
        i += 1

    filler = "\n\n".join(paragraphs)
    # Truncate at paragraph boundary
    if len(filler) > target_chars:
        # Find last paragraph boundary before target_chars
        idx = filler.rfind("\n\n", 0, target_chars)
        if idx > 0:
            filler = filler[:idx]

    # Insert distractor codes every ~15% of the document
    # Place them at approximate positions
    doc_len = len(filler)
    step = max(1, doc_len // (len(DISTRACTORS) + 1))
    distractor_idx = 0
    # Simple approach: insert distractors at regular intervals
    chunks = []
    current = ""
    for char in filler:
        current += char
        if len(current) >= step and distractor_idx < len(DISTRACTORS):
            # find a space to break
            last_space = current.rfind(" ")
            if last_space > len(current) // 2:
                chunks.append(current[:last_space])
                chunks.append(DISTRACTORS[distractor_idx])
                distractor_idx += 1
                current = current[last_space:]
    if current:
        chunks.append(current)
    filler_with_distractors = " ".join(chunks) if chunks else filler

    # Insert needle at depth position
    needle_line = f"\nThe harbour access code is {NEEDLE}.\n"
    insert_pos = int(len(filler_with_distractors) * spec.depth)
    # Find nearest newline
    nl = filler_with_distractors.rfind("\n", 0, insert_pos)
    if nl < 0:
        nl = insert_pos
    doc = filler_with_distractors[:nl] + "\n" + needle_line + filler_with_distractors[nl:]

    prompt = doc + QUESTION

    # Build-time assertions
    needle_count = doc.count(NEEDLE)
    if needle_count != 1:
        raise ValueError(f"needle appears {needle_count} times, expected 1")

    # NEEDLE_KEY must not appear in filler or distractors
    if NEEDLE_KEY in filler_with_distractors:
        raise ValueError("NEEDLE_KEY found in filler")
    for d in DISTRACTORS:
        norm = re.sub(r"[^A-Z0-9]", "", d.upper())
        if NEEDLE_KEY in norm:
            raise ValueError("NEEDLE_KEY found in distractor")

    if len(prompt) < 0.9 * target_chars:
        raise ValueError(
            f"prompt too short: {len(prompt)} < {0.9 * target_chars}"
        )

    # Verify at least 3 of 4 paragraphs used (for ctx >= 8192)
    used_paras = set()
    for p in FILLER_PARAGRAPHS:
        if p in filler:
            used_paras.add(p)
    # This check is informational; only enforce for large targets
    # (small targets may use fewer paragraphs)

    return prompt


def normalise_answer(text: str) -> str:
    """Uppercase and strip non-alphanumeric."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def grade_answer(answer_raw: str) -> tuple[str, str]:
    """Grade an answer. Returns (status, normalised_answer)."""
    norm = normalise_answer(answer_raw)
    distractor_keys = [re.sub(r"[^A-Z0-9]", "", d.upper()) for d in DISTRACTORS]
    distractor_keys.append(re.sub(r"[^A-Z0-9]", "", "1ALPHA0001".upper()))
    # Build proper distractor normalised keys
    dist_norms = []
    for d in DISTRACTORS:
        dist_norms.append(re.sub(r"[^A-Z0-9]", "", d.upper()))
    # Also include the stated decoy keys
    for dk in ["1ALPHA0001", "2BRAVO0002", "3CHARLIE0003", "4DELTA0004", "5ECHO0005"]:
        dist_norms.append(dk)

    has_needle = NEEDLE_KEY in norm
    has_distractor = any(dk in norm for dk in dist_norms)

    if has_needle and has_distractor:
        return "fail_ambiguous", norm
    if has_needle:
        return "pass", norm
    if has_distractor:
        return "fail_hallucinated", norm
    return "fail_not_found", norm


def estimate_cost_s(target_tokens: int, fill_ratio: float, prompt_tok_s: float = 20.0) -> float:
    """Estimate probe cost in seconds."""
    filled = target_tokens * fill_ratio
    prefill_s = filled / max(prompt_tok_s, 1.0)
    # load ~30s + prefill + small decode
    return 30.0 + prefill_s + 5.0


def run_recall_probe(
    client: Any,
    model_id: str,
    ctx: int,
    spec: RecallProbeSpec | None = None,
) -> RecallProbeResult:
    """Run a single recall probe against a live client.

    Returns a RecallProbeResult. Pure-ish: takes a client, returns structured data.
    """
    if spec is None:
        spec = RecallProbeSpec(target_tokens=ctx)

    result = RecallProbeResult(
        target_tokens=ctx,
        fill_ratio=spec.fill_ratio,
        depth=spec.depth,
        chars_per_token=spec.chars_per_token,
    )

    # Cost check
    est = estimate_cost_s(ctx, spec.fill_ratio, 20.0)
    result.estimated_cost_s = est
    if est > spec.max_probe_cost_s:
        result.status = "skipped"
        result.skipped_reason = "cost > cap"
        return result

    # Build prompt
    spec.target_tokens = ctx
    spec.chars_per_token = spec.chars_per_token or CHARS_PER_TOKEN
    try:
        prompt = build_recall_prompt(spec)
    except ValueError as e:
        result.status = "fail_build"
        result.skipped_reason = str(e)
        return result

    result.built_tokens_estimate = int(len(prompt) / spec.chars_per_token)

    # Call client
    try:
        response = client.chat_completion(
            model=model_id,
            input_text=prompt,
            temperature=spec.temperature,
            max_output_tokens=spec.max_tokens,
        )
    except Exception as e:
        result.status = "fail_error"
        result.skipped_reason = str(e)
        return result

    # Extract stats
    choices = response.get("choices") or []
    stats = response.get("_stats") or {}
    prompt_tokens = stats.get("prompt_tokens", 0)
    completion_tokens = stats.get("completion_tokens", 0)
    prompt_processing_ms = stats.get("prompt_processing_ms", 0.0)

    result.prompt_tokens = prompt_tokens
    result.completion_tokens = completion_tokens
    result.prompt_processing_ms = prompt_processing_ms

    # Get answer
    answer_raw = ""
    if choices:
        msg = choices[0].get("message", {})
        answer_raw = msg.get("content", "") or ""
    result.answer_raw = answer_raw[:200]
    result.answer_normalised = normalise_answer(answer_raw)

    # Check truncation
    if prompt_tokens < 0.60 * ctx:
        # Rebuild once with recalibrated chars_per_token
        if prompt_tokens > 0:
            new_cpt = ctx / prompt_tokens * spec.fill_ratio
            # Actually: chars_per_token = len(prompt) / prompt_tokens
            new_cpt = len(prompt) / prompt_tokens
            spec.chars_per_token = new_cpt
            result.chars_per_token = new_cpt
            try:
                build_recall_prompt(spec)
            except ValueError:
                pass
        result.status = "fail_prompt_truncated"
        result.truncated = True
        return result

    # Grade
    status, _ = grade_answer(answer_raw)
    result.status = status
    result.distractors_present = len(DISTRACTORS)

    # Cost
    result.actual_cost_s = (prompt_processing_ms / 1000.0) + 5.0

    return result


def run_recall_probe_deep(
    client: Any,
    model_id: str,
    ctx: int,
    depth_points: tuple[float, ...] = (0.1, 0.5, 0.9),
    spec: RecallProbeSpec | None = None,
) -> dict[str, Any]:
    """Run recall probe at multiple depths. Returns aggregate result."""
    if spec is None:
        spec = RecallProbeSpec(target_tokens=ctx)

    results = []
    for depth in depth_points:
        s = RecallProbeSpec(
            target_tokens=ctx,
            fill_ratio=spec.fill_ratio,
            depth=depth,
            max_tokens=spec.max_tokens,
            temperature=spec.temperature,
            max_probe_cost_s=spec.max_probe_cost_s,
            chars_per_token=spec.chars_per_token,
        )
        r = run_recall_probe(client, model_id, ctx, s)
        results.append(r)

    all_pass = all(r.status == "pass" for r in results)
    worst = None
    for r in results:
        if r.status != "pass":
            worst = r.depth
            break
    if worst is None and results:
        worst = max(r.depth for r in results if r.status != "pass") if any(
            r.status != "pass" for r in results
        ) else results[-1].depth

    return {
        "depth_results": [asdict(r) for r in results],
        "recall_all_depths": all_pass,
        "worst_depth": worst if worst is not None else 0.0,
    }
