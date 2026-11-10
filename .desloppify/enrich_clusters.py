"""Add action steps to the triage clusters."""

import os
import pathlib
import subprocess

exe = pathlib.Path(os.environ["APPDATA"]) / "Python" / "Python314" / "Scripts" / "desloppify.exe"

updates = {
    "cli-workflow-extraction": (
        "Extract preflight, host lifecycle, run execution and rendering from cli/main.py.",
        ["Extract preflight and host lifecycle into services",
         "Move run execution and report rendering into a workflow service",
         "Thin the Typer command bodies to parse/compose/render adapters"],
    ),
    "settings-boundary-typing": (
        "One typed AdvancedSettings boundary and BenchmarkService factory.",
        ["Define AdvancedSettings at the CLI/API boundary",
         "Add build_benchmark_service(settings) and use it from CLI and API",
         "Type defaults/duel payloads with TypedDicts",
         "Normalize skip phases to enums internally"],
    ),
    "error-handling-audit": (
        "Replace copied silent catches with one logged best-effort helper.",
        ["Add a best-effort helper that logs with exc_info",
         "Replace copied except/pass blocks in optimizer and routes",
         "Document the layer error contract (clients raise, services return outcomes)",
         "Flatten retry and success-condition branches"],
    ),
    "api-contracts": (
        "Response models, one error mapping and one presenter path.",
        ["Add response models to the untyped routes",
         "Add one exception-to-HTTP mapping layer",
         "Consolidate config response enrichment into one presenter",
         "Replace manual route registration with a supported pattern"],
    ),
    "services-structure": (
        "Split the flat services package and retire the legacy client boundary.",
        ["Split services/ into capability subpackages",
         "Split domain/models.py by aggregate",
         "Port discovery/inspector.py to services/lm_studio.py",
         "Move current-run globals into app.state"],
    ),
    "report-and-test-config": (
        "Split the report builder and the 244-line _test_config.",
        ["Extract report section builders that return lines",
         "Split _test_config into load/measure/evaluate/record steps"],
    ),
    "tests-conventions": (
        "Choose a canonical test root and add transport-level contract tests.",
        ["Choose one canonical test root or document unit vs integration markers",
         "Add httpx.MockTransport contract tests for LM Studio and Ollama",
         "Document the dataclass vs Pydantic boundary"],
    ),
    "security-and-docs": (
        "Add an optional remote API token and align docstrings with side effects.",
        ["Add an optional token for mutating routes when remote bind is allowed",
         "Align long-function docstrings with their side effects"],
    ),
}


def run(args):
    result = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


for name, (description, steps) in updates.items():
    rc, out = run(["plan", "cluster", "update", name, "--description", description, "--steps", *steps])
    print(f"update {name}: rc={rc} {out.strip()[-200:]}")

rc, out = run(["plan", "cluster", "list", "--verbose"])
print("=== clusters ===")
print(out[-3500:])
