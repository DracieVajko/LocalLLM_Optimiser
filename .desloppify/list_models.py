import httpx

response = httpx.get("http://127.0.0.1:1234/api/v1/models", timeout=10)
print("status", response.status_code)
for model in response.json().get("models", []):
    quant = (model.get("quantization") or {}).get("name") or "?"
    size_gb = round((model.get("size_bytes") or 0) / 1024**3, 2)
    print(
        f"{model.get('key')} | {model.get('display_name')} | {quant} | "
        f"{size_gb} GB | ctx {model.get('max_context_length')}"
    )
