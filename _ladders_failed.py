import subprocess, sys, os
models = [
    "nvidia-nemotron-3.5-bolt-e4b",
    "openai-gpt-oss-20b-claude-4.5-opus-heretic-uncensored-i1",
]
for m in models:
    print(f"\n===== LADDER: {m} =====", flush=True)
    cmd = [sys.executable, "-m", "lm_optimizer", "lab", "context-explorer", m,
           "--min-context", "2048", "--max-context", "262144", "--repetitions", "1"]
    r = subprocess.run(cmd, cwd=os.getcwd())
    print(f"exit code for {m}: {r.returncode}", flush=True)
print("\nFAILED-MODEL LADDERS DONE")
