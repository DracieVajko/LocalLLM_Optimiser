# Implementation Plan: Deep Research Features

**Date:** 2026-11-06  
**Source:** Deep research prompt + Design document `docs/specs/2026-11-06-deep-research-design.md`  
**Status:** Implementation

## 1. Tasks

| ID | Task | Depends On | Status |
|----|------|------------|--------|
| 1 | Implement `clean_tests` CLI command with `--dry-run` and `--failed-count` | None | Pending |
| 2 | Verify Ollama defaults API completeness | Ollama client exists | Pending |
| 3 | Document CLI/API interfaces with exact signatures | All features implemented | Pending |
| 4 | Write tests following failing→verification→passing cycle | Features implemented | Pending |
| 5 | Run full test suite and verify all pass | Tests written | Pending |

## 2. Task 1: `clean_tests` CLI Command

### 2.1 Specification

```
lm-optimizer clean_tests [--dry-run] [--failed-count N]
```

- Remove artifacts and DB entries with `status='failed'` after `N` consecutive failures
- Only within project folder (`results/`, `data/`); never delete outside directory
- Default `--dry-run`: list candidates without deleting
- Default `--failed-count`: 2
- Backup files older than `BACKUP_KEEP` (10) are also cleaned

### 2.2 Implementation Details

- Add `clean_tests` command to `lm_optimizer/cli/main.py`
- Query `run_repo` for runs with `status='failed'`
- Check consecutive failures per model
- Delete failed run DB rows and associated artifact directories
- Preserve successful runs and backups younger than retention limit

### 2.3 Acceptance Criteria

- `--dry-run` lists candidates without deleting
- `--failed-count N` respects the threshold
- Only failed runs are deleted; successful runs preserved
- Path traversal attacks rejected (only within project folder)

## 3. Task 2: Ollama Defaults API Verification

### 3.1 Existing Endpoints

| Endpoint | Method | Status |
|----------|--------|--------|
| `GET /ollama-default` | GET | ✓ Implemented |
| `POST /runs/{run_id}/save-ollama-default` | POST | ✓ Implemented |
| `POST /ollama-default/restore` | POST | ✓ Implemented |
| `GET /runs/{run_id}/ollama-default-diff` | GET | ✓ Implemented |
| `POST /runs/{run_id}/verify-ollama-default` | POST | ✓ Implemented |

All Ollama default endpoints are implemented. Verification complete.

## 4. Task 3: CLI/API Documentation

### 4.1 CLI Commands

| Command | Description |
|---------|-------------|
| `optimize <model>` | Phase-A tuning + preset + report |
| `benchmark <model>` | 5-test suite, one config |
| `compare <model>` | A/B configs on same tests |
| `auto [models]` | Smart→precision→ladder→matrix→optimize |
| `fit [models]` | Max-context ladder per KV path |
| `ctx <model>` | Geometric context sweep + bisect |
| `pause <id>` / `resume <id>` | Graceful pause + resume |
| `checkpoints` | List interrupt checkpoints |
| `param-matrix` | Parameter control matrix |
| `apply / restore / presets / runs` | Presets and history management |
| `cleanup_test_runs` | Remove test runs |
| `lab context-explorer <model>` | 1.5x context ladder + fill ratios |
| `lab quality-lab <model>` | Deterministic quality tasks |
| `lab recommend` | Model recommendations |
| `lab duel <a> <b>` | Controlled/best-profile duel |
| `lab sandbox --task T --model M` | Single-model sandbox task |
| `lab sandbox-all --model M` | All sandbox tasks for one model |
| `lab save-default <run-id>` | Persist winner as LM Studio default |
| `lab diff-default <run-id>` | Show defaults diff |
| `lab restore-default <model>` | Restore defaults from backup |
| `clean_tests` | Remove failed runs (NEW) |

### 4.2 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/runs` | GET | List optimization runs |
| `/api/runs/{run_id}` | GET | Get run detail |
| `/api/runs/{run_id}/pause` | POST | Pause run |
| `/api/runs/{run_id}/resume` | POST | Resume run |
| `/api/duels` | GET | List duels |
| `/api/duels/{job_id}` | GET | Get duel result |
| `/api/sandbox` | POST | Start model-vs-model duel |
| `/api/sandbox/{job_id}` | GET | Poll duel result |
| `/api/sandbox/runs` | GET | List single-model sandbox runs |
| `/api/sandbox/run/{index}` | GET | Get sandbox task run detail |
| `/api/sandbox/files?file_path=...` | GET | Serve sandbox artifact file |
| `/api/sandbox/runs/clear-failed` | POST | Delete failed sandbox runs |
| `/api/optimize` | POST | Start optimization |
| `/api/status` | GET | Connection + capabilities |
| `/api/models` | GET | List local models |
| `/api/models/{model_id}` | GET | Model detail |
| `/api/stats` | GET | Dashboard quick-stats |
| `/api/checkpoints` | GET | List checkpoints |
| `/api/lab/sandbox-tasks` | GET | List sandbox task definitions |
| `/api/lab/sandbox-run` | POST | Start single-model sandbox task |
| `/api/lab/sandbox-run/{job_id}` | GET | Poll sandbox task result |

## 5. Task 4: Tests

All tests follow the failing→verification→passing cycle:

1. Write failing test
2. Implement feature
3. Verify test passes
4. Commit

## 6. Completion Checklist

- [ ] Exact request and all constraints met
- [ ] Relevant supplied files inspected
- [ ] Key claims traceable; sources support the exact claim
- [ ] No invented source, quote, DOI, URL, page, spec, result, or action
- [ ] Conflicts, assumptions, limits, untested conditions disclosed
- [ ] Numbers, units, percentages, tables, figures agree
- [ ] Technical choices fit datasheets, constraints, failure cases, safety
- [ ] Conclusions within the evidence; structure coherent; wording original; terminology consistent
- [ ] Files exist and contain the intended content
