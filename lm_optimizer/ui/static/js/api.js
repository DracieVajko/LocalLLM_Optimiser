// LM Studio Auto Optimizer - API Client

export const API = {
    baseURL: '/api',
    // Every async operation has a timeout: never loading forever (§15).
    timeoutMs: 12000,
    // In-flight GET dedup: concurrent identical polls share one fetch, so a
    // runaway loop (or N tabs in one page context) cannot multiply traffic.
    _inflight: new Map(),
    // Double-submit guard: mutating endpoints can only have one in-flight
    // request at a time, so double-clicking "Start Optimization" can't fire twice.
    _submitting: new Set(),

    async request(endpoint, options = {}) {
        const method = (options.method || 'GET').toUpperCase();
        const key = method === 'GET' ? `${method} ${endpoint}` : null;
        if (key && this._inflight.has(key)) return this._inflight.get(key);
        // Double-submit guard for mutating endpoints.
        if (method !== 'GET' && this._submitting.has(endpoint)) {
            throw new Error('Request already in flight: ' + endpoint);
        }
        if (method !== 'GET') this._submitting.add(endpoint);
        const pending = this._requestInner(endpoint, options).finally(() => {
            if (key && this._inflight.get(key) === pending) this._inflight.delete(key);
            if (method !== 'GET') this._submitting.delete(endpoint);
        });
        if (key) this._inflight.set(key, pending);
        return pending;
    },

    async _requestInner(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const timeoutMs = options.timeoutMs || this.timeoutMs;
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
            signal: controller.signal,
        };
        delete config.timeoutMs;

        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        let response;
        try {
            response = await fetch(url, config);
        } catch (error) {
            if (error && error.name === 'AbortError') {
                throw new Error(`Request timed out after ${timeoutMs}ms: ${endpoint}`);
            }
            throw new Error(`Network error: ${(error && error.message) || error}`);
        } finally {
            clearTimeout(timer);
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            // FastAPI 422 detail is an array of {loc, msg, type}; never
            // surface "[object Object]" to the user.
            let detail = error.detail;
            if (Array.isArray(detail)) {
                detail = detail.map(item => {
                    if (item && typeof item === 'object') {
                        const loc = Array.isArray(item.loc) ? item.loc.join('.') : '';
                        return loc ? `${loc}: ${item.msg || 'invalid'}` : (item.msg || 'invalid');
                    }
                    return String(item);
                }).join('; ');
            } else if (detail && typeof detail === 'object') {
                detail = detail.message || JSON.stringify(detail);
            }
            const err = new Error(detail || `HTTP ${response.status}`);
            err.status = response.status;
            throw err;
        }

        return response.json();
    },

    // Status
    async getStatus() {
        return this.request('/status');
    },

    async testConnection(url) {
        return this.request('/connect', {
            method: 'POST',
            body: { url },
            timeoutMs: 30000,
        });
    },

    // Models
    async getModels() {
        return this.request('/models');
    },

    // Dashboard quick-stats (documented meanings, server-computed).
    async getStats() {
        return this.request('/stats');
    },

    // Preview/apply stale-running reconciliation.
    async reconcileRuns(apply = false) {
        return this.request(`/runs/reconcile${apply ? '?apply=true' : ''}`, { method: 'POST' });
    },

    async getModel(modelId) {
        return this.request(`/models/${encodeURIComponent(modelId)}`, { timeoutMs: 30000 });
    },

    // Optimization
    async startOptimization(request) {
        return this.request('/optimize', {
            method: 'POST',
            body: request,
            timeoutMs: 60000,
        });
    },

    async pauseOptimization(runId) {
        return this.request(`/optimize/${runId}/pause`, { method: 'POST' });
    },

    async resumeOptimization(runId) {
        return this.request(`/optimize/${runId}/resume`, { method: 'POST' });
    },

    // New pause/resume for any run (not just current optimizer)
    async pauseRun(runId) {
        return this.request(`/runs/${runId}/pause`, { method: 'POST' });
    },

    async resumeRunFromCheckpoint(runId) {
        return this.request(`/runs/${runId}/resume`, { method: 'POST' });
    },

    async cancelOptimization(runId) {
        return this.request(`/optimize/${runId}/cancel`, { method: 'POST' });
    },

    async getOptimizationProgress(runId) {
        return this.request(`/optimize/${runId}/progress`);
    },

    async resumeRun(runId) {
        return this.request(`/optimize/${runId}/resume-run`, { method: 'POST' });
    },

    async getCheckpoints() {
        return this.request('/checkpoints');
    },

    // Runs
    async getRuns(limit = 50, offset = 0, modelId = null) {
        const params = new URLSearchParams({ limit, offset });
        if (modelId) params.append('model_id', modelId);
        return this.request(`/runs?${params}`);
    },

    async getRun(runId) {
        return this.request(`/runs/${runId}`);
    },

    async getConfigurations(runId) {
        return this.request(`/runs/${runId}/configurations`);
    },

    async getConfiguration(runId, configId) {
        return this.request(`/runs/${runId}/configurations/${configId}`);
    },

    async getParetoFrontier(runId) {
        return this.request(`/runs/${runId}/pareto`);
    },

    async exportRun(runId, format = 'json') {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);
        try {
            const response = await fetch(`${this.baseURL}/runs/${runId}/export?format=${format}`, { signal: controller.signal });
            if (!response.ok) {
                const err = new Error('Export failed');
                err.status = response.status;
                throw err;
            }
            return response.blob();
        } catch (error) {
            if (error && error.name === 'AbortError') {
                throw new Error(`Request timed out after ${this.timeoutMs}ms: export`);
            }
            throw error;
        } finally {
            clearTimeout(timer);
        }
    },

    async judge(request) {
        return this.request('/judge', {
            method: 'POST',
            body: JSON.stringify(request),
            timeoutMs: 120000,
        });
    },

    async exportLmStudioConfig(runId) {
        return this.request(`/runs/${runId}/export-config`);
    },

    async getDefaultDiff(runId) {
        return this.request(`/runs/${runId}/default-diff`);
    },

    async saveLmStudioDefault(runId, dryRun = false) {
        const query = dryRun ? '?dry_run=true' : '';
        return this.request(`/runs/${runId}/save-default${query}`, { method: 'POST', timeoutMs: 60000 });
    },

    // Apply Configuration
    async applyConfiguration(request) {
        return this.request('/apply', {
            method: 'POST',
            body: request,
            timeoutMs: 60000,
        });
    },

    async restorePrevious(modelId) {
        return this.request(`/restore/${modelId}`, { method: 'POST' });
    },

    // Presets
    async getPresets(modelId = null) {
        const params = modelId ? `?model_id=${encodeURIComponent(modelId)}` : '';
        return this.request(`/presets${params}`);
    },

    async savePreset(preset) {
        return this.request('/presets', {
            method: 'POST',
            body: preset,
        });
    },

    async deletePreset(presetId) {
        return this.request(`/presets/${presetId}`, { method: 'DELETE' });
    },

    async applyPreset(presetId) {
        return this.request(`/presets/${presetId}/apply`, { method: 'POST' });
    },

    // Sandbox duels
    async getDuels(limit = 50, offset = 0) {
        return this.request(`/duels?limit=${limit}&offset=${offset}`);
    },

    async getDuel(jobId) {
        return this.request(`/duels/${jobId}`);
    },

    async deleteDuel(jobId) {
        return this.request(`/duels/${jobId}`, { method: 'DELETE' });
    },

    async deleteRun(runId) {
        return this.request(`/runs/${runId}`, { method: 'DELETE' });
    },

    async abandonRun(runId) {
        return this.request(`/runs/${runId}/abandon`, { method: 'POST' });
    },

    // Settings
    async getSettings() {
        return this.request('/settings');
    },

    async updateSettings(settings) {
        return this.request('/settings', {
            method: 'PUT',
            body: settings,
        });
    },
};