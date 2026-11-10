"""Re-review the three stale subjective dimensions (run 20261103_155918)."""

import json
from pathlib import Path

SRC = Path(".desloppify/subagents/runs")
DST = SRC / "20261103_155918" / "results"
DST.mkdir(parents=True, exist_ok=True)

SPECS = {
    7: {
        "src": SRC / "20261103_135748" / "results" / "batch-7.raw.txt",
        "dim": "dependency_health",
        "score": 84.0,
        "drop": {"stale_requirements_txt"},
        "issues": [
            {
                "dimension": "dependency_health",
                "identifier": "unpinned_transitives",
                "summary": "No lock file pins transitive dependency versions",
                "related_files": ["pyproject.toml", "requirements.txt"],
                "evidence": [
                    "Both files use lower bounds (>=) and there is no lock file in the repository.",
                    "A fresh install can resolve different transitive versions over time.",
                ],
                "suggestion": "Add a lock file (uv.lock or pip-compile output) for reproducible installs and CI.",
                "confidence": "medium",
                "impact_scope": "module",
                "fix_scope": "single_edit",
            }
        ],
        "append": [
            "requirements.txt now mirrors pyproject and no longer lists GPUtil; the dependency lists cannot drift silently.",
        ],
        "rationale": "GPUtil and both import cycles are gone, and requirements.txt is aligned with pyproject. A focused dependency set with no known maintenance hazards supports a strong score.",
    },
    12: {
        "src": SRC / "20261103_135748" / "results" / "batch-12.raw.txt",
        "dim": "authorization_consistency",
        "score": 72.0,
        "drop": {"no_token_for_remote"},
        "issues": [
            {
                "dimension": "authorization_consistency",
                "identifier": "local_routes_unauthenticated",
                "summary": "Loopback routes remain unauthenticated by design",
                "related_files": ["lm_optimizer/api/routes.py", "lm_optimizer/web_main.py"],
                "evidence": [
                    "Local loopback traffic bypasses the token guard so the UI keeps working.",
                    "This is documented as a localhost-only threat model.",
                ],
                "suggestion": "If the tool ships as a multi-user service, add a user/session model rather than extending the loopback bypass.",
                "confidence": "medium",
                "impact_scope": "module",
                "fix_scope": "multi_file_refactor",
            }
        ],
        "append": [
            "Remote bind now requires LM_OPTIMIZER_API_TOKEN; non-loopback mutating requests must send X-API-Token, with tests covering refusal and acceptance.",
        ],
        "rationale": "Localhost-only default, a startup guard, audit events and a token for remote mutating requests address the practical risk for this local tool. A full user/permission model remains the next step.",
    },
    13: {
        "src": SRC / "20261103_151531" / "results" / "batch-13.raw.txt",
        "dim": "ai_generated_debt",
        "score": 75.0,
        "drop": {"docstring_scope_drift"},
        "issues": [
            {
                "dimension": "ai_generated_debt",
                "identifier": "defensive_api_error_translation",
                "summary": "API handlers still catch broad exceptions and build ad-hoc 500 responses",
                "related_files": ["lm_optimizer/api/routes.py"],
                "evidence": [
                    "Several handlers catch Exception and raise HTTPException(500, detail=str(e)) inline.",
                    "The pattern is defensive boilerplate rather than one mapped error boundary.",
                ],
                "suggestion": "Move exception-to-HTTP translation into one middleware or exception handler and keep handler bodies focused on the domain call.",
                "confidence": "medium",
                "impact_scope": "module",
                "fix_scope": "multi_file_refactor",
            }
        ],
        "append": [
            "save_best_report and _test_config docstrings now list their side effects and outputs.",
        ],
        "rationale": "Silent catches are logged, service print output is gone, and the remaining long-function docstrings now describe their side effects. Comments stay sparse and why-focused.",
    },
}

for idx, spec in SPECS.items():
    payload = json.loads(spec["src"].read_text(encoding="utf-8"))
    dim = spec["dim"]
    payload["batch"] = dim
    payload["batch_index"] = idx
    payload["assessments"][dim] = spec["score"]
    notes = payload["dimension_notes"][dim]
    notes["evidence"] = list(notes.get("evidence", [])) + spec["append"]
    notes["issues_preventing_higher_score"] = spec["rationale"]
    judgment = payload["dimension_judgment"][dim]
    judgment["score_rationale"] = spec["rationale"]
    payload["issues"] = spec.get("issues", []) + [
        issue for issue in payload.get("issues", [])
        if issue.get("identifier") not in spec["drop"]
    ]
    (DST / f"batch-{idx}.raw.txt").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(f"batch-{idx} {dim} {spec['score']} issues={len(payload['issues'])}")
