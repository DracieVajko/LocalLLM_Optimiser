"""Static web validator for the sandbox web task (stdlib only).

Implements the parts of spec §13.1 that are achievable WITHOUT a browser
and WITHOUT new dependencies:

- required files exist,
- HTML parses (well-formed enough for html.parser),
- viewport meta, title, lang attribute,
- no external scripts/styles (the sandbox forbids network by default),
- media queries present (responsive intent),
- heading hierarchy (single h1),
- images have alt attributes,
- form inputs have labels or aria-label,
- inline JavaScript parses (via `node --check` when Node is available).

What it explicitly does NOT do (honest limits): layout rendering,
screenshots, computed contrast, real click-through functional tests. Those
need a real browser engine and are listed as missing in docs/README.md.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

# --- HTML parsing -----------------------------------------------------------


@dataclass
class HtmlFacts:
    """Facts collected from one HTML document."""

    title: str = ""
    lang: str = ""
    has_viewport: bool = False
    h1_count: int = 0
    headings: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    inputs: list[dict] = field(default_factory=list)
    labels: int = 0
    label_for: list[str] = field(default_factory=list)
    scripts_external: list[str] = field(default_factory=list)
    styles_external: list[str] = field(default_factory=list)
    inline_scripts: list[str] = field(default_factory=list)
    inline_styles: list[str] = field(default_factory=list)
    parse_error: str = ""

    @property
    def has_media_query(self) -> bool:
        return any("@media" in style for style in self.inline_styles)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.facts = HtmlFacts()
        self._in_title = False
        self._in_script = False
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        facts = self.facts
        if tag == "html":
            facts.lang = attr.get("lang", "")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            if attr.get("name", "").lower() == "viewport":
                facts.has_viewport = True
        elif tag == "h1":
            facts.h1_count += 1
            facts.headings.append("h1")
        elif tag in ("h2", "h3", "h4", "h5", "h6"):
            facts.headings.append(tag)
        elif tag == "img":
            facts.images.append({"src": attr.get("src", ""), "alt": attr.get("alt")})
        elif tag in ("input", "select", "textarea"):
            facts.inputs.append(
                {
                    "type": attr.get("type", "text"),
                    "id": attr.get("id", ""),
                    "aria_label": attr.get("aria-label", ""),
                    "hidden": attr.get("type", "").lower() == "hidden",
                }
            )
        elif tag == "label":
            facts.labels += 1
            facts.label_for.append(attr.get("for", ""))
        elif tag == "script":
            src = attr.get("src", "")
            if src:
                facts.scripts_external.append(src)
            self._in_script = not src
        elif tag == "style":
            self._in_style = True
        elif tag == "link":
            href = attr.get("href", "")
            if href:
                facts.styles_external.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_script = False
        elif tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        facts = self.facts
        if self._in_title:
            facts.title += data
        elif self._in_script:
            facts.inline_scripts.append(data)
        elif self._in_style:
            facts.inline_styles.append(data)


def parse_html(text: str) -> HtmlFacts:
    """Parse HTML and return the collected facts (never raises)."""
    parser = _Parser()
    try:
        parser.feed(text or "")
        parser.close()
    except Exception as e:  # noqa: BLE001
        parser.facts.parse_error = f"{type(e).__name__}: {e}"[:160]
    return parser.facts


# --- JavaScript validation --------------------------------------------------

#: The JavaScript parsed cleanly.
JS_VALID = "valid"
#: The JavaScript is broken (the validator reported a syntax error).
JS_INVALID = "invalid"
#: There was no JavaScript to validate.
JS_EMPTY = "empty"
#: The validator could not run - the JavaScript was NOT validated.
JS_UNAVAILABLE = "unavailable"

#: Module syntax (``import`` / ``export``) means the source must be parsed as
#: an ES module. Node 20 hides syntax errors in a ``.js`` file that contains
#: module syntax (its module-detection retry swallows them), while Node 26
#: reports them. Writing the probe file as ``.mjs`` makes every Node version
#: parse it as a module.
_MODULE_SYNTAX = re.compile(
    r"^\s*(?:import\s+[\w{*'\"$]|import\s*\(|import\.meta"
    r"|export\s+(?:default|const|let|var|function|async|class|\*|\{))",
    re.MULTILINE,
)

#: Seconds a single ``node --check`` may take.
JS_CHECK_TIMEOUT_S = 20


@dataclass
class JsValidation:
    """Result of one JavaScript validation pass.

    ``state`` distinguishes "the code is broken" from "the code could not be
    checked" - an unavailable validator must never look like a success.
    """

    state: str
    errors: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def passed(self) -> bool:
        """True only when there was nothing wrong and nothing unverified."""
        return self.state in (JS_VALID, JS_EMPTY)

    @property
    def verified(self) -> bool:
        """True only when a validator actually inspected the source."""
        return self.state == JS_VALID


def _looks_like_module(code: str) -> bool:
    return bool(_MODULE_SYNTAX.search(code))


def validate_javascript(
    scripts: list[str],
    *,
    node_path: str | None = None,
) -> JsValidation:
    """Syntax-check JavaScript sources with ``node --check``.

    Returns a :class:`JsValidation`:

    * ``valid`` - every source parsed,
    * ``invalid`` - at least one source has a syntax error,
    * ``empty`` - there was no source to check,
    * ``unavailable`` - the validator could not run (no Node runtime, the
      runtime could not be started, or it timed out). The JavaScript was then
      **not** validated, which is never reported as a success.
    """
    sources = [code for code in scripts if code and code.strip()]
    if not sources:
        return JsValidation(state=JS_EMPTY, detail="no JavaScript to validate")

    if node_path is None:
        node_path = shutil.which("node")
    if not node_path:
        return JsValidation(
            state=JS_UNAVAILABLE,
            detail=(
                "not validated: the Node.js runtime was not found "
                "(install Node.js to validate JavaScript)"
            ),
        )

    errors: list[str] = []
    for index, code in enumerate(sources):
        suffix = ".mjs" if _looks_like_module(code) else ".js"
        path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=suffix, delete=False, encoding="utf-8"
            ) as handle:
                handle.write(code)
                path = handle.name
            proc = subprocess.run(
                [node_path, "--check", path],
                capture_output=True,
                text=True,
                timeout=JS_CHECK_TIMEOUT_S,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return JsValidation(
                state=JS_UNAVAILABLE,
                detail=(
                    f"not validated: node --check timed out after "
                    f"{JS_CHECK_TIMEOUT_S}s"
                ),
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            return JsValidation(
                state=JS_UNAVAILABLE,
                detail=f"not validated: the Node.js runtime could not run ({exc})",
            )
        finally:
            if path:
                Path(path).unlink(missing_ok=True)

        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "").strip()
            for ugly in (path or "", (path or "").replace("\\", "/")):
                if ugly:
                    message = message.replace(ugly, "inline.js")
            errors.append(f"script {index}: {message[:200]}" or f"script {index}: failed")

    if errors:
        return JsValidation(state=JS_INVALID, errors=errors, detail="; ".join(errors)[:300])
    return JsValidation(state=JS_VALID, detail="JavaScript parses")


# --- checks -----------------------------------------------------------------


@dataclass
class WebCheck:
    """One static check result."""

    name: str
    passed: bool
    detail: str = ""
    critical: bool = False


def _is_external(url: str) -> bool:
    return bool(re.match(r"^https?://", (url or "").strip(), re.IGNORECASE))


def js_syntax_errors(scripts: list[str]) -> list[str]:
    """Deprecated: use :func:`validate_javascript`.

    Kept for callers that only care about syntax errors. It cannot express
    the "validator unavailable" state - use :func:`validate_javascript` when
    the difference between "broken" and "not checked" matters.
    """
    return validate_javascript(scripts).errors


def validate_web_files(files: dict[str, str]) -> list[WebCheck]:
    """Static validation of the produced web files.

    Returns one WebCheck per criterion. Callers merge these into the
    sandbox score (critical checks can veto the attempt).
    """
    checks: list[WebCheck] = []
    html_name = None
    for name in files:
        if name.lower().endswith((".html", ".htm")):
            html_name = name
            break

    checks.append(
        WebCheck(
            "index_html_exists",
            html_name is not None,
            f"html files: {[n for n in files if n.lower().endswith(('.html', '.htm'))]}",
            critical=True,
        )
    )
    if html_name is None:
        return checks

    facts = parse_html(files[html_name])
    checks.append(
        WebCheck(
            "html_not_empty",
            len(files[html_name].strip()) >= 50,
            f"{len(files[html_name].strip())} chars",
            critical=True,
        )
    )
    checks.append(
        WebCheck(
            "html_parses",
            not facts.parse_error,
            facts.parse_error or "ok",
            critical=True,
        )
    )
    checks.append(WebCheck("has_title", bool(facts.title.strip()), facts.title[:80]))
    checks.append(
        WebCheck("has_lang", bool(facts.lang.strip()), facts.lang or "missing")
    )
    checks.append(
        WebCheck("has_viewport", facts.has_viewport, "viewport meta")
    )
    checks.append(
        WebCheck("single_h1", facts.h1_count == 1, f"h1 count={facts.h1_count}")
    )
    checks.append(
        WebCheck("has_media_query", facts.has_media_query, "responsive intent")
    )

    external_scripts = [s for s in facts.scripts_external if _is_external(s)]
    external_styles = [s for s in facts.styles_external if _is_external(s)]
    checks.append(
        WebCheck(
            "no_external_scripts",
            not external_scripts,
            f"external: {external_scripts[:3]}",
        )
    )
    checks.append(
        WebCheck(
            "no_external_styles",
            not external_styles,
            f"external: {external_styles[:3]}",
        )
    )

    missing_alt = [
        img["src"] for img in facts.images if img.get("alt") is None
    ]
    checks.append(
        WebCheck(
            "images_have_alt",
            not missing_alt,
            f"missing alt: {missing_alt[:3]}",
        )
    )

    unlabeled = [
        inp
        for inp in facts.inputs
        if not inp["hidden"]
        and not inp["aria_label"]
        and (not inp["id"] or inp["id"] not in facts.label_for)
    ]
    # A wrapping <label> (no `for`) can also cover inputs; if labels exist
    # but none use `for`, assume wrapping coverage rather than false-failing.
    if facts.labels and not any(facts.label_for):
        unlabeled = []
    checks.append(
        WebCheck(
            "inputs_labeled",
            not unlabeled,
            f"unlabeled inputs: {len(unlabeled)}",
        )
    )

    validation = validate_javascript(facts.inline_scripts)
    checks.append(
        WebCheck(
            "inline_js_parses",
            validation.passed,
            validation.detail or ("; ".join(validation.errors)[:300] or "ok"),
        )
    )
    return checks
