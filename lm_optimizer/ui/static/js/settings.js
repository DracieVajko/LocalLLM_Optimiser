// LM Studio Auto Optimizer - Settings Page

import { API } from './api.js?v=17';
import { UI } from './ui.js?v=17';

const SettingsPage = {
    state: {
        settings: null,
    },

    async init() {
        UI.init();
        await this.loadSettings();
        this.render();
        this.attachEvents();
        // Show the installed version immediately, then check for updates.
        try {
            const v = await API.request('/version');
            const el = document.getElementById('installed-version');
            if (el) el.textContent = v.version || '—';
        } catch (e) { /* leave placeholder */ }
    },

    async loadSettings() {
        try {
            this.state.settings = await API.getSettings();
        } catch (error) {
            console.error('Failed to load settings:', error);
            this.state.settings = {
                lm_studio_url: 'http://127.0.0.1:1234',
                web_host: '127.0.0.1',
                web_port: 8080,
                default_profile: 'balanced',
                default_quality_threshold: 0.97,
                default_benchmark_repetitions: 3,
                default_validation_repetitions: 5,
                auto_unload_after_tests: true,
                timeout_seconds: 300,
            };
        }
    },

    render() {
        const main = document.getElementById('main-content');
        main.innerHTML = `
            <div class="max-w-3xl mx-auto space-y-8">
                <div>
                    <h1 class="text-3xl font-bold text-gray-900">Settings</h1>
                    <p class="text-gray-500 mt-1">Configure LM Studio Auto Optimizer</p>
                </div>

                <form id="settings-form" class="space-y-8">
                    <!-- LM Studio Connection -->
                    <div class="card">
                        <div class="card-header">
                            <h2 class="text-lg font-semibold text-gray-900">LM Studio Connection</h2>
                        </div>
                        <div class="card-body space-y-4">
                            <div>
                                <label class="form-label">LM Studio URL</label>
                                <div class="flex gap-2">
                                    <input type="url" id="lm-studio-url" name="lm_studio_url" value="${this.state.settings.lm_studio_url}" class="form-input flex-1" placeholder="http://127.0.0.1:1234">
                                    <button type="button" id="test-connection" class="btn btn-outline">Test Connection</button>
                                </div>
                                <p class="text-xs text-gray-500 mt-1">The URL of your LM Studio instance with Developer API enabled.</p>
                            </div>
                            <div class="mt-4">
                                <label class="form-label">API Token</label>
                                <input type="password" id="api-token" name="api_token" value="" class="form-input" placeholder="${this.state.settings.api_token ? '•••••••• (unchanged)' : 'Optional API token'}">
                                <p class="text-xs text-gray-500 mt-1">Required for remote (non-loopback) clients. Leave blank to keep the stored token unchanged; type a new value to replace it.</p>
                            </div>
                        </div>
                    </div>

                    <!-- Web UI -->
                    <div class="card">
                        <div class="card-header">
                            <h2 class="text-lg font-semibold text-gray-900">Web UI</h2>
                        </div>
                        <div class="card-body grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="form-label">Host</label>
                                <input type="text" id="web-host" name="web_host" value="${this.state.settings.web_host}" class="form-input">
                            </div>
                            <div>
                                <label class="form-label">Port</label>
                                <input type="number" id="web-port" name="web_port" value="${this.state.settings.web_port}" min="1" max="65535" class="form-input">
                            </div>
                        </div>
                    </div>

                    <!-- Default Optimization Settings -->
                    <div class="card">
                        <div class="card-header">
                            <h2 class="text-lg font-semibold text-gray-900">Default Optimization Settings</h2>
                        </div>
                        <div class="card-body grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="form-label">Default Profile</label>
                                <select name="default_profile" class="form-input form-select">
                                    <option value="speed" ${this.state.settings.default_profile === 'speed' ? 'selected' : ''}>Speed</option>
                                    <option value="balanced" ${this.state.settings.default_profile === 'balanced' ? 'selected' : ''}>Balanced</option>
                                    <option value="context" ${this.state.settings.default_profile === 'context' ? 'selected' : ''}>Context</option>
                                    <option value="quality" ${this.state.settings.default_profile === 'quality' ? 'selected' : ''}>Quality</option>
                                </select>
                            </div>
                            <div>
                                <label class="form-label">Default Quality Threshold</label>
                                <input type="number" name="default_quality_threshold" value="${this.state.settings.default_quality_threshold}" step="0.01" min="0.9" max="1" class="form-input">
                            </div>
                            <div>
                                <label class="form-label">Benchmark Repetitions</label>
                                <input type="number" name="default_benchmark_repetitions" value="${this.state.settings.default_benchmark_repetitions}" min="1" max="10" class="form-input">
                            </div>
                            <div>
                                <label class="form-label">Validation Repetitions</label>
                                <input type="number" name="default_validation_repetitions" value="${this.state.settings.default_validation_repetitions}" min="1" max="10" class="form-input">
                            </div>
                        </div>
                    </div>

                    <!-- Behavior -->
                    <div class="card">
                        <div class="card-header">
                            <h2 class="text-lg font-semibold text-gray-900">Behavior</h2>
                        </div>
                        <div class="card-body space-y-4">
                            <div class="form-checkbox">
                                <input type="checkbox" name="auto_unload_after_tests" id="auto-unload" ${this.state.settings.auto_unload_after_tests ? 'checked' : ''} class="form-checkbox-input">
                                <label for="auto-unload">Auto unload model after each test</label>
                            </div>
                            <div>
                                <label class="form-label">Timeout (seconds)</label>
                                <input type="number" name="timeout_seconds" value="${this.state.settings.timeout_seconds}" min="60" max="3600" class="form-input">
                            </div>
                        </div>
                    </div>

                    <!-- Hardware Overrides -->
                    <div class="card">
                        <div class="card-header">
                            <h2 class="text-lg font-semibold text-gray-900">Hardware Overrides (Optional)</h2>
                        </div>
                        <div class="card-body grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div>
                                <label class="form-label">GPU VRAM (GB) - Auto if empty</label>
                                <input type="number" name="gpu_vram_gb" value="${this.state.settings.gpu_vram_gb ?? ''}" step="0.1" min="0" class="form-input" placeholder="Auto-detect">
                            </div>
                            <div>
                                <label class="form-label">System RAM (GB) - Auto if empty</label>
                                <input type="number" name="system_ram_gb" value="${this.state.settings.system_ram_gb ?? ''}" step="0.1" min="0" class="form-input" placeholder="Auto-detect">
                            </div>
                            <div>
                                <label class="form-label">GPU Name - Auto if empty</label>
                                <input type="text" name="gpu_name" value="${this.state.settings.gpu_name ?? ''}" class="form-input" placeholder="Auto-detect">
                            </div>
                        </div>
                        <p class="text-xs text-gray-500">Leave empty to auto-detect. Override only if auto-detection is incorrect.</p>
                    </div>

                    <!-- Save Button -->
                    <div class="flex justify-end">
                        <button type="submit" class="btn btn-success">Save Settings</button>
                    </div>
                </form>

                <!-- Updates -->
                <div class="card">
                    <div class="card-header">
                        <h2 class="text-lg font-semibold text-gray-900">Updates</h2>
                    </div>
                    <div class="card-body space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="font-medium">Installed version</span>
                            <span class="font-mono" id="installed-version">loading…</span>
                        </div>
                        <div class="flex items-center justify-between">
                            <span class="font-medium">Latest on GitHub</span>
                            <span class="font-mono" id="latest-version">—</span>
                        </div>
                        <div class="flex gap-2">
                            <button id="check-updates" class="btn btn-outline">Check for updates</button>
                            <button id="apply-update" class="btn btn-success hidden">Apply update</button>
                        </div>
                        <p id="update-status" class="text-xs text-gray-500"></p>
                    </div>
                </div>

                <!-- Danger Zone -->
                <div class="card border-red-200">
                    <div class="card-header border-red-200">
                        <h2 class="text-lg font-semibold text-red-600">Danger Zone</h2>
                    </div>
                    <div class="card-body space-y-4">
                        <div class="p-4 bg-red-50 rounded-lg border border-red-200">
                            <h3 class="font-medium text-red-800">Reset All Data</h3>
                            <p class="text-sm text-red-600 mt-1">This will permanently delete all optimization runs, configurations, presets, and benchmark data. This action cannot be undone.</p>
                            <button id="reset-data" class="btn btn-danger mt-3" disabled title="Not available: requires backend endpoint">Delete All Data</button>
                        </div>

                        <div class="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
                            <h3 class="font-medium text-yellow-800">Export All Data</h3>
                            <p class="text-sm text-yellow-600 mt-1">Download a complete backup of all runs, presets, and settings as JSON.</p>
                            <button id="export-all" class="btn btn-outline mt-3" disabled title="Not available: requires backend endpoint">Export Everything</button>
                        </div>

                        <div class="p-4 bg-blue-50 rounded-lg border border-blue-200">
                            <h3 class="font-medium text-blue-800">Import Data</h3>
                            <p class="text-sm text-blue-600 mt-1">Restore from a previously exported backup file.</p>
                            <div class="flex gap-2 mt-3">
                                <input type="file" id="import-file" accept=".json" class="form-input flex-1">
                                <button id="import-data" class="btn btn-primary" disabled title="Not available: requires backend endpoint">Import</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    },

    attachEvents() {
        // Form submit
        const form = document.getElementById('settings-form');
        if (form) {
            form.addEventListener('submit', (e) => this.saveSettings(e));
        }

        // Test connection
        const testBtn = document.getElementById('test-connection');
        if (testBtn) {
            testBtn.addEventListener('click', () => this.testConnection());
        }

        // Updates
        const checkBtn = document.getElementById('check-updates');
        if (checkBtn) checkBtn.addEventListener('click', () => this.checkUpdates());
        const applyBtn = document.getElementById('apply-update');
        if (applyBtn) applyBtn.addEventListener('click', () => this.applyUpdate());

        // Danger zone buttons
        document.getElementById('reset-data')?.addEventListener('click', () => this.resetData());
        document.getElementById('export-all')?.addEventListener('click', () => this.exportAll());
        document.getElementById('import-data')?.addEventListener('click', () => this.importData());
    },

    async saveSettings(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        const settings = {};

        for (const [key, value] of formData.entries()) {
            if (value === 'on') {
                settings[key] = true;
            } else if (value === '' && key !== 'lm_studio_url') {
                // Skip empty optional fields
                continue;
            } else {
                // Convert numeric values, but never coerce the API token
                // (a numeric-looking token must stay a string).
                if (key !== 'api_token' && !isNaN(value) && value !== '') {
                    settings[key] = value.includes('.') ? parseFloat(value) : parseInt(value);
                } else {
                    settings[key] = value;
                }
            }
        }

        // Handle checkboxes not in form data
        const checkboxes = form.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(cb => {
            if (!formData.has(cb.name)) {
                settings[cb.name] = false;
            }
        });

        try {
            await API.updateSettings(settings);
            UI.showToast('Settings saved successfully', 'success');
            this.state.settings = { ...this.state.settings, ...settings };
        } catch (error) {
            UI.showToast('Failed to save settings: ' + error.message, 'error');
        }
    },

    async testConnection() {
        const url = document.getElementById('lm-studio-url').value;
        const btn = document.getElementById('test-connection');

        if (!url) {
            UI.showToast('Please enter a URL', 'error');
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Testing...';

        try {
            await API.testConnection(url);
            UI.showToast('Connection successful!', 'success');
        } catch (error) {
            UI.showToast('Connection failed: ' + error.message, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Test Connection';
        }
    },

    async checkUpdates() {
        const status = document.getElementById('update-status');
        const installed = document.getElementById('installed-version');
        const latest = document.getElementById('latest-version');
        const applyBtn = document.getElementById('apply-update');
        if (status) status.textContent = 'Checking GitHub…';
        try {
            const data = await API.request('/update/check');
            if (installed) installed.textContent = data.current || '—';
            if (latest) latest.textContent = data.latest || '—';
            if (data.update_available) {
                if (status) status.textContent = 'Update available: ' + data.current + ' → ' + data.latest;
                if (applyBtn) applyBtn.classList.remove('hidden');
            } else {
                if (status) status.textContent = data.error ? data.error : 'You are up to date.';
                if (applyBtn) applyBtn.classList.add('hidden');
            }
        } catch (err) {
            if (status) status.textContent = 'Check failed: ' + ((err && err.message) || err);
        }
    },

    async applyUpdate() {
        const status = document.getElementById('update-status');
        const applyBtn = document.getElementById('apply-update');
        if (!window.confirm('Download and apply the update? A backup of the current files is written first. The app must be restarted afterwards.')) {
            return;
        }
        if (applyBtn) applyBtn.disabled = true;
        if (status) status.textContent = 'Downloading and applying update…';
        try {
            const apply = await API.request('/update/apply', {
                method: 'POST',
                headers: {
                    'X-Confirm-Update': 'yes',
                    'X-Requested-With': 'fetch',
                },
            });
            if (apply && apply.success) {
                if (status) status.textContent = 'Updated ' + apply.from + ' → ' + apply.to + '. Restart the app.';
                UI.showToast('Update applied — restart LM Studio Optimizer', 'success');
            } else {
                if (status) status.textContent = 'Update failed: ' + (apply?.reason || 'unknown');
                UI.showToast('Update failed', 'error');
            }
        } catch (err) {
            if (status) status.textContent = 'Apply failed: ' + ((err && err.message) || err);
            UI.showToast('Update failed', 'error');
        } finally {
            if (applyBtn) applyBtn.disabled = false;
        }
    },

    async resetData() {
        // Disabled in UI: no backend endpoint available.
        UI.showToast('Data reset not available — requires backend endpoint', 'warning');
    },

    async exportAll() {
        UI.showToast('Full export not available — requires backend endpoint', 'warning');
    },

    async importData() {
        UI.showToast('Import not available — requires backend endpoint', 'warning');
    },
};

    // readyState-safe boot: deferred modules may evaluate after DOMContentLoaded.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => SettingsPage.init());
} else {
    SettingsPage.init();
}