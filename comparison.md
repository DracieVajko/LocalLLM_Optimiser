# Model bake-off comparison

Generated from `results/bakeoff/runs.jsonl`. Generation time includes the model's thinking phase where supported.

## Model totals (load once + all tasks)

| model | mean score | tasks passed | load_s | total gen_s | total_s | tokens | tok/s | thinking_chars |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| nvidia-nemotron-3.5-bolt-e4b | 0.641 | 3/6 | 10.9 | 331.9 | 342.8 | 9391 | 28.29 | 13133 |
| qwen3.8-9b-distill | 0.111 | 0/3 | 30.0 | 246.5 | 276.5 | 2048 | 8.31 | 0 |

## Per-task detail

| model | task | score | pass | repair | load_s | gen_s | total_s | tokens | tok/s | thinking_chars | context | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nvidia-nemotron-3.5-bolt-e4b | blender_skyblock | 0.8485 | False | 2 | 12.5 | 110.5 | 122.9 | 4644 | 42.05 | 4521 | 8192 | - |
| nvidia-nemotron-3.5-bolt-e4b | email_write | 0 | False | 0 | 10.9 | 0 | 10.9 | 0 | 0 | 0 | 8192 | - |
| nvidia-nemotron-3.5-bolt-e4b | email_write | 0 | False | 0 | 11.1 | 0 | 11.1 | 0 | 0 | 0 | 8192 | AttributeError: 'dict' object has no attribute 'usage' |
| nvidia-nemotron-3.5-bolt-e4b | email_write | 1 | True | 1 | 10.9 | 23.3 | 34.2 | 1134 | 48.67 | 4011 | 8192 | - |
| nvidia-nemotron-3.5-bolt-e4b | email_write | 1 | True | 1 | 12.5 | 30.6 | 43.1 | 1134 | 37.01 | 4011 | 8192 | - |
| nvidia-nemotron-3.5-bolt-e4b | web_dashboard | 1 | True | 0 | 12.5 | 167.5 | 179.9 | 2479 | 14.8 | 590 | 8192 | - |
| qwen3.8-9b-distill | blender_skyblock | 0 | False | 0 | 30 | 0 | 30 | 0 | 0 | 0 | 8192 | HTTPStatusError: Server error '500 Internal Server Error' for url 'http://127.0. |
| qwen3.8-9b-distill | email_write | 0.3333 | False | 1 | 30 | 246.5 | 276.5 | 2048 | 8.31 | 0 | 8192 | - |
| qwen3.8-9b-distill | web_dashboard | 0 | False | 0 | 30 | 0 | 30 | 0 | 0 | 0 | 8192 | HTTPStatusError: Server error '500 Internal Server Error' for url 'http://127.0. |

## KV cache placement (same weights, context 8192)

| model | context | KV_GPU load_s | KV_RAM load_s | KV_GPU tok/s | KV_RAM tok/s | faster |
|---|---|---:|---:|---:|---:|---|
| qwen3.8-9b-distill | 8192 | 20.2 | 10.7 | 7.9 | 6.18 | GPU |

