"""Replace the manual APIRoute recreation with include_router."""

import pathlib

path = pathlib.Path("lm_optimizer/api/main.py")
text = path.read_text(encoding="utf-8")
start = text.index("# API routes - manually include")
marker = "    app.router.routes.append(route)\n"
end = text.index(marker, start) + len(marker)
replacement = (
    'app.include_router(api_router, prefix="/api")\n'
    "app.include_router(ws_router)\n"
)
new_text = text[:start] + replacement + text[end:]
path.write_text(new_text, encoding="utf-8")
print("changed", new_text != text, "bytes", len(text), len(new_text))
print("has include_router:", "app.include_router" in path.read_text(encoding="utf-8"))
