// Model sandbox: text / html / scene duels. POST /api/sandbox, poll, render.
(function () {
    var kind = 'text';
    function el(id) { return document.getElementById(id); }
    function out(html) { el('sb-out').innerHTML = html; }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }

    document.querySelectorAll('.sb-kind').forEach(function (b) {
        b.addEventListener('click', function () {
            kind = b.dataset.kind;
            document.querySelectorAll('.sb-kind').forEach(function (x) {
                x.classList.toggle('btn-primary', x === b);
                x.classList.toggle('btn-outline', x !== b);
            });
            renderPresets();
        });
    });

    var PRESETS = {
        text: [
            { label: 'Hash-table explainer', prompt: 'Write a concise explanation of how a hash table works in 3-4 sentences.' },
            { label: 'find_duplicates coding', prompt: 'Write a Python function `find_duplicates(nums: list[int]) -> list[int]` that returns all duplicate integers in a list: O(n) time, O(1) extra space (excluding output), handle negatives, ascending order. Only the function definition with docstring.' },
        ],
        html: [
            { label: 'Coffee landing page', prompt: 'Build a small responsive landing page for a fictional coffee shop: hero header, three feature cards, footer. Single self-contained HTML file, embedded CSS, clean modern look.' },
            { label: 'Todo app', prompt: 'Build a functional single-file todo app: add, toggle and delete tasks with localStorage persistence. Embedded CSS and vanilla JavaScript, no frameworks.' },
        ],
        scene: [
            { label: 'Skyblock demo', prompt: null }, // filled below (full spec)
            { label: 'Simple spinner', prompt: 'Build a single self-contained HTML file with one slowly rotating 3D cube (Three.js via CDN), dark background, nothing else.' },
        ],
    };
    PRESETS.scene[0].prompt = 'Act as an expert frontend engineer, WebGL specialist, and 3D game developer. '
        + 'Generate a complete, production-grade, single-file HTML page containing a mini-3D voxel game render '
        + 'inspired by "Minecraft Skyblock" using Three.js. Self-contained in one code block, no placeholders, '
        + 'no omissions. HTML5 boilerplate, Three.js via reliable public CDN (cdnjs or unpkg), CSS reset, '
        + 'canvas 100% viewport, dark background. Floating island of individual colored voxels '
        + '(BoxGeometry + MeshStandardMaterial or Basic for performance): green grass top layer, brown/grey '
        + 'dirt-stone under-layers, semi-transparent blue water in a carved recess, minimalist voxel oak tree '
        + '(brown trunk, green foliage) on the grass. Camera: OrbitControls from CDN if safe, else smooth '
        + 'automatic 360-degree orbit. Lights: AmbientLight plus DirectionalLight with shadows. '
        + 'Performance: grouped meshes, requestAnimationFrame 60 FPS loop, dynamic resize handling, vanilla JS only. '
        + 'Output only the complete HTML code, starting directly with <!DOCTYPE html>.';

    // Initialise AFTER PRESETS exists: calling renderPresets() earlier threw
    // a TypeError and aborted the whole script (no presets, no run handler).
    renderPresets();
    var firstKind = document.querySelector('.sb-kind');
    if (firstKind) {
        firstKind.classList.add('btn-primary');
        firstKind.classList.remove('btn-outline');
    }

    function renderPresets() {
        var box = el('sb-presets');
        box.innerHTML = '';
        (PRESETS[kind] || []).forEach(function (p) {
            var b = document.createElement('button');
            b.className = 'btn btn-outline btn-sm';
            b.textContent = p.label;
            b.addEventListener('click', function () { el('sb-prompt').value = p.prompt; });
            box.appendChild(b);
        });
    }

    function toTextFallback(select) {
        var input = document.createElement('input');
        input.id = select.id;
        input.className = select.className;
        input.placeholder = 'model id (list failed to load)';
        select.replaceWith(input);
    }

    async function loadModels() {
        try {
            var r = await fetch('/api/models');
            if (!r.ok) throw new Error('HTTP ' + r.status);
            var j = await r.json();
            var models = j.models || [];
            if (!models.length) throw new Error('no models');
            ['sb-a', 'sb-b'].forEach(function (id) {
                var sel = el(id);
                sel.innerHTML = '';
                models.forEach(function (m, i) {
                    var o = document.createElement('option');
                    o.value = m.id;
                    o.textContent = m.name || m.id;
                    sel.appendChild(o);
                });
                sel.selectedIndex = id === 'sb-b' ? Math.min(1, models.length - 1) : 0;
            });
        } catch (e) {
            toTextFallback(el('sb-a'));
            toTextFallback(el('sb-b'));
            out('<p class="text-sm text-yellow-700">Model list failed to load — type model IDs manually. (' + esc((e && e.message) || e) + ')</p>');
        }
    }
    loadModels();

    async function poll(id) {
        for (var i = 0; i < 180; i++) {
            var r = await fetch('/api/sandbox/' + encodeURIComponent(id));
            var j = await r.json();
            if (j.status === 'done') return j;
            if (j.status === 'failed') throw new Error(j.error || 'sandbox failed');
            await new Promise(function (res) { setTimeout(res, 3000); });
        }
        throw new Error('Timed out waiting for duel result');
    }

    function fileBlock(side, label, base) {
        if (!side || !side.ok || !side.file_path) {
            return '<h4 class="font-bold">' + label + '</h4>'
                + '<p class="text-red-600 text-sm">' + esc((side && side.error) || 'failed') + '</p>';
        }
        // job_id/side mirrored into the file-serving route path
        var parts = String(side.file_path).split('/');
        var url = '/sandbox/files/' + parts[0] + '/' + parts[1] + '/index.html';
        return '<h4 class="font-bold">' + label + ' <span class="text-xs font-normal text-gray-500">'
            + esc(side.tok_s ? side.tok_s.toFixed(1) + ' tok/s' : '') + '</span></h4>'
            + '<p class="text-xs font-mono text-gray-500">results/sandbox/' + esc(side.file_path) + '</p>'
            + '<p class="mt-1"><a class="underline text-blue-600" target="_blank" rel="noopener" href="' + url + '">Open index.html</a></p>'
            + '<iframe sandbox="" src="' + url + '" class="w-full mt-2 border rounded" style="height:420px" title="' + label + ' preview"></iframe>'
            + (base ? '' : '');
    }

    el('sb-run').addEventListener('click', async function () {
        try {
            var a = (el('sb-a').value || '').trim();
            var b = (el('sb-b').value || '').trim();
            var p = (el('sb-prompt').value || '').trim();
            if (!a || !b) throw new Error('Both model A and B are required');
            if (!p) throw new Error('Prompt is required');
            out('<p class="text-sm">Duel running: A first, unload, then B...</p>');
            var r = await fetch('/api/sandbox', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_a: a, model_b: b, prompt: p, kind: kind }),
            });
            if (!r.ok) {
                var e = await r.json().catch(function () { return {}; });
                throw new Error((e && e.detail) || ('HTTP ' + r.status));
            }
            var started = await r.json();
            var done = await poll(started.job_id);
            var d = done.result || {};
            var head = '<h3 class="font-bold">Done'
                + (d.faster && d.faster !== 'draw' ? ' — ' + esc(d.faster) + ' was faster' : d.faster === 'draw' ? ' — tie' : '')
                + '</h3>';
            if (kind === 'text') {
                out(head + '<div class="grid md:grid-cols-2 gap-4 mt-2">'
                    + '<div><h4 class="font-bold">A: ' + esc(d.model_a) + '</h4>'
                    + '<p class="text-xs text-gray-500">' + esc(d.side_a.tok_s ? d.side_a.tok_s.toFixed(1) + ' tok/s' : (d.side_a.error || '')) + '</p>'
                    + '<pre class="font-mono text-xs bg-gray-50 p-2 rounded overflow-auto max-h-96 mt-1">' + esc(d.side_a.text || d.side_a.error || '') + '</pre></div>'
                    + '<div><h4 class="font-bold">B: ' + esc(d.model_b) + '</h4>'
                    + '<p class="text-xs text-gray-500">' + esc(d.side_b.tok_s ? d.side_b.tok_s.toFixed(1) + ' tok/s' : (d.side_b.error || '')) + '</p>'
                    + '<pre class="font-mono text-xs bg-gray-50 p-2 rounded overflow-auto max-h-96 mt-1">' + esc(d.side_b.text || d.side_b.error || '') + '</pre></div>'
                    + '</div>');
            } else {
                out(head + '<div class="grid md:grid-cols-2 gap-4 mt-2">'
                    + '<div>' + fileBlock(d.side_a, 'A: ' + esc(d.model_a)) + '</div>'
                    + '<div>' + fileBlock(d.side_b, 'B: ' + esc(d.model_b)) + '</div>'
                    + '</div>');
            }
        } catch (e) {
            out('<p class="text-red-600 text-sm">Error: ' + esc((e && e.message) || e) + '</p>');
        }
    });
    // --- Sandbox history, grouped per model -------------------------------
    var historyRuns = [];
    var pinnedRun = null;
    var expandedModel = null;
    var openTask = null;
    var selectedRun = null;
    var expandIds = {};

    function badge(ok, text) {
        return '<span class="badge ' + (ok ? 'badge-success' : 'badge-error') + '">' + text + '</span>';
    }

    function resultBadge(x) {
        if ((x.status || 'measured') === 'not_measured') {
            return '<span class="badge badge-warning">NOT MEASURED</span>';
        }
        return x.final_success ? badge(true, 'PASS') : badge(false, 'FAIL');
    }

    function scoreText(x) {
        return x.final_score == null ? '-' : Number(x.final_score).toFixed(2);
    }

    function groupRuns(runs) {
        var models = {};
        runs.forEach(function (x, idx) {
            var name = x.model || 'unknown';
            if (!models[name]) {
                models[name] = { model: name, runs: [], last: '', best: null, bestTask: '' };
            }
            var group = models[name];
            group.runs.push({ index: idx, run: x });
            if ((x.ts || '') > group.last) group.last = x.ts || '';
            if (x.final_score != null && (group.best == null || x.final_score > group.best)) {
                group.best = x.final_score;
                group.bestTask = x.task || '';
            }
        });
        return Object.keys(models).map(function (k) { return models[k]; }).sort(function (a, b) {
            return (b.last || '').localeCompare(a.last || '');
        });
    }

    function originOf(run) {
        return (run.origin || 'local') === 'frontier' ? 'frontier' : 'local';
    }

    // Each entry is addressed by its stable run_id, because a prune (or a new
    // run) shifts the numeric positions of the newest-first list.
    function runsFor(origin, model, task) {
        return historyRuns.map(function (x, idx) {
            return { id: x.run_id || String(idx), run: x };
        })
            .filter(function (r) {
                if (originOf(r.run) !== origin) return false;
                if ((r.run.model || 'unknown') !== model) return false;
                return task == null || (r.run.task || 'unknown') === task;
            })
            .sort(function (a, b) {
                return (b.run.ts || '').localeCompare(a.run.ts || '');
            });
    }

    function tasksOf(origin, model) {
        var byTask = {};
        runsFor(origin, model).forEach(function (r) {
            var name = r.run.task || 'unknown';
            if (!byTask[name]) byTask[name] = [];
            byTask[name].push(r);
        });
        return Object.keys(byTask).sort().map(function (name) {
            return { task: name, runs: byTask[name] };
        });
    }

    function modelDomId(key) {
        return expandIds[key] || ('sb-expand-' + String(key || '').replace(/[^a-z0-9]+/gi, '_'));
    }

    function renderTable(runs, origin, title) {
        if (!runs.length) return '';
        var groups = groupRuns(runs);
        var note = origin === 'frontier'
            ? '<p class="text-xs text-gray-500 mb-2">Scored from API output, not measured on this hardware.</p>'
            : '<p class="text-xs text-gray-500 mb-2">' + runs.length + ' local run(s) on this machine.</p>';
        return '<h3 class="text-sm font-semibold mt-4 mb-1">' + esc(title) + '</h3>' + note
            + '<div class="table-container"><table class="table"><thead><tr>'
            + '<th>Model</th><th>Runs</th><th>Tests</th><th>Best</th><th>Last run</th><th></th>'
            + '</tr></thead><tbody>'
            + groups.map(function (g, groupIndex) {
                var key = origin + '::' + g.model;
                expandIds[key] = 'sb-expand-' + origin + '-' + groupIndex;
                var tasks = tasksOf(origin, g.model);
                var open = expandedModel === key;
                var apiBadge = origin === 'frontier'
                    ? ' <span class="badge badge-warning">API</span>'
                    : '';
                return '<tr class="history-model' + (open ? ' is-open' : '') + '" data-model="'
                    + esc(g.model) + '" data-origin="' + origin + '" data-key="' + esc(key)
                    + '" tabindex="0" role="button" aria-expanded="' + (open ? 'true' : 'false')
                    + '" style="cursor:pointer">'
                    + '<td class="font-mono text-xs"><span class="sb-chevron mr-1 text-gray-400">'
                    + (open ? '▾' : '▸') + '</span>' + esc(g.model) + apiBadge + '</td>'
                    + '<td class="font-mono">' + g.runs.length + '</td>'
                    + '<td class="font-mono">' + tasks.length + '</td>'
                    + '<td>' + (g.best == null ? '-' : scoreText({ final_score: g.best })
                        + ' <span class="text-xs text-gray-500">' + esc(g.bestTask) + '</span>') + '</td>'
                    + '<td class="font-mono text-xs">' + esc(g.last || '') + '</td>'
                    + '<td class="text-right text-gray-400">' + (open ? '▾' : '▸') + '</td>'
                    + '</tr>'
                    + '<tr class="sb-expand-row" data-origin="' + origin + '" data-model="'
                    + esc(g.model) + '"><td colspan="6" class="p-0">'
                    + '<div class="sb-expand" id="' + modelDomId(key) + '"></div></td></tr>';
            }).join('')
            + '</tbody></table></div>';
    }

    function renderHistory() {
        var box = el('sb-runs');
        if (!historyRuns.length) {
            box.innerHTML = '<p class="text-sm text-gray-500">No sandbox task runs yet. Run one with '
                + '<code>python -m lm_optimizer.cli.main lab sandbox --task company_website --model &lt;model&gt;</code></p>';
            return;
        }
        var localRuns = historyRuns.filter(function (x) { return originOf(x) === 'local'; });
        var frontierRuns = historyRuns.filter(function (x) { return originOf(x) === 'frontier'; });
        expandIds = {};
        box.innerHTML = '<p class="text-xs text-gray-500 mb-2">' + historyRuns.length + ' run(s): '
            + localRuns.length + ' local, ' + frontierRuns.length
            + ' frontier. Click a model to expand its tests.</p>'
            + renderTable(localRuns, 'local', 'Local models (this hardware)')
            + renderTable(frontierRuns, 'frontier', 'Frontier (API) — not measured on this hardware');

        Array.prototype.forEach.call(box.querySelectorAll('tr.history-model'), function (row) {
            function toggle() {
                var key = row.dataset.key;
                expandedModel = expandedModel === key ? null : key;
                openTask = null;
                selectedRun = null;
                renderHistory();
                var reopened = document.querySelector('tr.history-model.is-open');
                if (reopened) reopened.focus();
            }
            row.addEventListener('click', toggle);
            row.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    toggle();
                }
            });
        });
        renderExpansion();
    }

    function renderExpansion() {
        if (!expandedModel) return;
        var separator = expandedModel.indexOf('::');
        if (separator < 0) return;
        var origin = expandedModel.slice(0, separator);
        var model = expandedModel.slice(separator + 2);
        var container = document.getElementById(modelDomId(expandedModel));
        if (!container) return;
        if (openTask) renderTaskDetail(container, origin, model, openTask);
        else renderTaskList(container, origin, model);
    }

    function renderTaskList(container, origin, model) {
        var tasks = tasksOf(origin, model);
        container.innerHTML = '<div class="p-3 bg-gray-50 border-t">'
            + '<table class="table"><thead><tr>'
            + '<th>Test</th><th>Result</th><th>Score</th><th>Date</th><th>Runs</th><th></th>'
            + '</tr></thead><tbody>'
            + tasks.map(function (t) {
                var latest = t.runs[0].run;
                return '<tr class="sb-test-row" data-task="' + esc(t.task) + '">'
                    + '<td class="font-mono text-xs">' + esc(t.task) + '</td>'
                    + '<td>' + resultBadge(latest) + '</td>'
                    + '<td class="font-mono">' + scoreText(latest) + '</td>'
                    + '<td class="font-mono text-xs">' + esc(latest.ts || '') + '</td>'
                    + '<td class="font-mono" title="' + t.runs.length + ' run(s) of this test">' + t.runs.length + '</td>'
                    + '<td class="text-right"><button class="btn btn-outline btn-sm view-test" data-task="'
                    + esc(t.task) + '">View</button></td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div>';

        Array.prototype.forEach.call(container.querySelectorAll('.view-test'), function (button) {
            button.addEventListener('click', function (event) {
                event.stopPropagation();
                openTask = button.dataset.task;
                selectedRun = null;
                renderExpansion();
            });
        });
    }

    function renderTaskDetail(container, origin, model, task) {
        var list = runsFor(origin, model, task);
        if (!list.length) {
            openTask = null;
            renderExpansion();
            return;
        }
        var selected = null;
        list.forEach(function (r) { if (r.id === selectedRun) selected = r; });
        if (!selected) selected = list[0];
        selectedRun = selected.id;

        var picker = list.length > 1
            ? '<select class="run-picker form-select text-xs" aria-label="Choose a run of this test">'
                + list.map(function (r) {
                    var key = (r.run.run_key || 'legacy').slice(0, 10);
                    return '<option value="' + esc(r.id) + '"'
                        + (r.id === selected.id ? ' selected' : '') + '>'
                        + esc((r.run.ts || '') + ' · ' + scoreText(r.run) + ' · ' + key) + '</option>';
                }).join('')
                + '</select>'
            : '';

        var pinBtn = pinnedRun === selected.id
            ? '<button class="btn btn-outline btn-sm" id="sb-unpin">Unpin</button>'
            : '<button class="btn btn-outline btn-sm" id="sb-pin">Pin</button>';
        var compareBtn = (pinnedRun != null && pinnedRun !== selected.id)
            ? '<button class="btn btn-outline btn-sm" id="sb-compare">Compare with pinned</button>'
            : '';

        container.innerHTML = '<div class="p-3 bg-gray-50 border-t">'
            + '<div class="flex flex-wrap items-center justify-between gap-2 mb-2">'
            + '<div class="flex items-center gap-2">'
            + '<button class="btn btn-outline btn-sm" id="sb-back-to-tests">← Back to tests</button>'
            + '<h4 class="font-bold">' + esc(task) + '</h4>'
            + '<span class="text-xs text-gray-500">' + list.length + ' run(s)</span>'
            + '</div><div class="flex items-center gap-2">' + picker + pinBtn + compareBtn + '</div>'
            + '</div><div id="sb-run-detail"><p class="text-sm text-gray-500">Loading run...</p></div></div>';

        el('sb-back-to-tests').addEventListener('click', function () {
            openTask = null;
            selectedRun = null;
            renderExpansion();
        });
        if (el('sb-pin')) {
            el('sb-pin').addEventListener('click', function () {
                pinnedRun = selected.id;
                renderExpansion();
            });
        }
        if (el('sb-unpin')) {
            el('sb-unpin').addEventListener('click', function () {
                pinnedRun = null;
                renderExpansion();
            });
        }
        if (el('sb-compare')) {
            el('sb-compare').addEventListener('click', function () {
                showCompareRuns(container, pinnedRun, selected.id);
            });
        }
        var pick = container.querySelector('.run-picker');
        if (pick) {
            pick.addEventListener('change', function () {
                selectedRun = pick.value;
                renderExpansion();
            });
        }

        loadRunDetail(selected.id);
    }

    var detailRequest = 0;

    async function loadRunDetail(runId) {
        var host = el('sb-run-detail');
        if (!host) return;
        var request = ++detailRequest;
        try {
            var r = await fetch('/api/sandbox/run-id/' + encodeURIComponent(runId));
            if (!r.ok) throw new Error('HTTP ' + r.status);
            var x = await r.json();
            if (request !== detailRequest) return;  // a newer pick won
            host.innerHTML = runDetailHtml(x);
        } catch (e) {
            if (request !== detailRequest) return;
            host.innerHTML = '<p class="text-sm text-red-600">Failed to load run detail: '
                + esc((e && e.message) || e) + '</p>'
                + '<button class="btn btn-outline btn-sm mt-2" id="sb-detail-retry">Retry</button>';
            var retry = el('sb-detail-retry');
            if (retry) {
                retry.addEventListener('click', function () { loadRunDetail(runId); });
            }
        }
    }

    function runDetailHtml(x) {
        var crit = (x.critical_failures || []).length
            ? '<ul class="text-xs text-red-600 mt-1">'
                + (x.critical_failures || []).map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('')
                + '</ul>'
            : '';
        var failing = [];
        (x.attempts || []).forEach(function (a) {
            (a.failing_checks || []).forEach(function (f) { failing.push(f); });
        });
        failing = failing.filter(function (v, i, arr) { return arr.indexOf(v) === i; });
        var failingHtml = failing.length
            ? '<ul class="text-xs text-red-600 mt-1">'
                + failing.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('')
                + '</ul>'
            : '<span class="text-xs text-gray-500">none</span>';
        var artifacts = (x.artifacts || []).length
            ? '<ul class="text-xs text-gray-600 mt-1">'
                + (x.artifacts || []).map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('')
                + '</ul>'
            : '<span class="text-xs text-gray-500">no files</span>';
        var blend = x.blend_file
            ? '<tr><td class="font-bold">Blend file</td><td class="font-mono text-xs">' + esc(x.blend_file)
                + '<div class="text-gray-500">Open it directly in Blender.</div></td></tr>'
            : '';

        return '<table class="table text-sm"><tbody>'
            + '<tr><td class="font-bold">Time</td><td>' + esc(x.ts || '') + '</td></tr>'
            + '<tr><td class="font-bold">Model</td><td class="font-mono">' + esc(x.model || '') + '</td></tr>'
            + '<tr><td class="font-bold">Task</td><td>' + esc(x.task || '') + '</td></tr>'
            + '<tr><td class="font-bold">Score</td><td class="font-mono">' + scoreText(x) + '</td></tr>'
            + '<tr><td class="font-bold">Result</td><td>' + resultBadge(x) + '</td></tr>'
            + '<tr><td class="font-bold">Status</td><td>' + esc(x.status || 'measured') + '</td></tr>'
            + '<tr><td class="font-bold">Repairs</td><td>' + (x.repair_count || 0) + '</td></tr>'
            + '<tr><td class="font-bold">Duration</td><td class="font-mono">'
            + (x.duration_s ? Number(x.duration_s).toFixed(0) + 's' : '-') + '</td></tr>'
            + '<tr><td class="font-bold">Workdir</td><td class="font-mono text-xs truncate" title="'
            + esc(x.workdir || '') + '">' + esc(x.workdir || '') + '</td></tr>'
            + blend
            + '<tr><td class="font-bold">Failing checks</td><td>' + failingHtml + '</td></tr>'
            + (crit ? '<tr><td class="font-bold">Critical failures</td><td>' + crit + '</td></tr>' : '')
            + (artifacts ? '<tr><td class="font-bold">Artifacts</td><td>' + artifacts + '</td></tr>' : '')
            + (x.error ? '<tr><td class="font-bold">Error</td><td class="text-red-600 text-xs">'
                + esc(x.error) + '</td></tr>' : '')
            + '</tbody></table>'
            + '<div class="mt-4"><h4 class="font-bold">Preview</h4>'
            + (x.artifacts || []).map(function (a) {
                var rel = x.workdir ? x.workdir.replace(/^results[\\/](sandbox|bakeoff)[\\/]/, '') + '/' + a : a;
                var safeRel = rel.replace(/\\/g, '/');
                if (/[.](html|htm)$/i.test(a)) {
                    return '<div class="mt-2 border rounded bg-black p-1">'
                        + '<iframe sandbox="" src="/sandbox/files?file_path=' + encodeURIComponent(safeRel) + '"'
                        + ' class="w-full border rounded" style="height:520px" title="' + esc(a) + ' preview"></iframe>'
                        + '</div>';
                }
                if (/[.](py|js|txt|json|md)$/i.test(a)) {
                    return '<details class="mt-2"><summary class="text-sm font-semibold cursor-pointer">'
                        + esc(a) + '</summary>'
                        + '<iframe src="/sandbox/files?file_path=' + encodeURIComponent(safeRel) + '"'
                        + ' class="w-full border rounded" style="height:320px" title="' + esc(a) + ' preview"></iframe>'
                        + '</details>';
                }
                return '<p class="text-xs text-gray-500 mt-2">' + esc(a) + '</p>';
            }).join('')
            + '</div>';
    }

    async function showCompareRuns(container, idA, idB) {
        container.innerHTML = '<p class="text-sm text-gray-500 p-3">Loading comparison...</p>';
        try {
            var responses = await Promise.all([
                fetch('/api/sandbox/run-id/' + encodeURIComponent(idA)),
                fetch('/api/sandbox/run-id/' + encodeURIComponent(idB)),
            ]);
            if (!responses[0].ok || !responses[1].ok) {
                throw new Error('HTTP ' + (responses[0].ok ? responses[1].status : responses[0].status));
            }
            var runs = await Promise.all(responses.map(function (r) { return r.json(); }));
            var html = '<div class="p-3 bg-gray-50 border-t">'
                + '<div class="flex items-center justify-between mb-2">'
                + '<h4 class="font-bold">Compare two runs</h4>'
                + '<button class="btn btn-outline btn-sm" id="sb-compare-back">Back</button>'
                + '</div><div class="grid md:grid-cols-2 gap-4">';
            runs.forEach(function (x) {
                var failing = [];
                (x.attempts || []).forEach(function (a) {
                    (a.failing_checks || []).forEach(function (f) { failing.push(f); });
                });
                failing = failing.filter(function (v, i, arr) { return arr.indexOf(v) === i; });
                var preview = (x.artifacts || []).map(function (a) {
                    var rel = x.workdir ? x.workdir.replace(/^results[\\/](sandbox|bakeoff)[\\/]/, '') + '/' + a : a;
                    var safeRel = rel.replace(/\\/g, '/');
                    if (/[.](html|htm)$/i.test(a)) {
                        return '<div class="mt-2 border rounded bg-black p-1">'
                            + '<iframe sandbox="" src="/sandbox/files?file_path=' + encodeURIComponent(safeRel) + '"'
                            + ' class="w-full border rounded" style="height:260px" title="' + esc(a) + ' preview"></iframe>'
                            + '</div>';
                    }
                    if (/[.](py|js|txt|json|md)$/i.test(a)) {
                        return '<details class="mt-2" open><summary class="text-sm font-semibold cursor-pointer">'
                            + esc(a) + '</summary>'
                            + '<iframe src="/sandbox/files?file_path=' + encodeURIComponent(safeRel) + '"'
                            + ' class="w-full border rounded" style="height:260px" title="' + esc(a) + ' preview"></iframe>'
                            + '</details>';
                    }
                    return '<p class="text-xs text-gray-500 mt-2">' + esc(a) + '</p>';
                }).join('');
                html += '<div class="border rounded p-3">'
                    + '<div class="font-mono text-xs text-gray-500 mb-1">' + esc(x.ts || '') + '</div>'
                    + '<div class="font-mono text-sm font-semibold mb-1">' + esc(x.model || '') + '</div>'
                    + '<div class="text-sm mb-2">' + esc(x.task || '') + ' ' + resultBadge(x) + '</div>'
                    + '<div class="text-xs text-gray-600 mb-2">score ' + scoreText(x) + ' · '
                    + (x.duration_s ? Number(x.duration_s).toFixed(0) + 's' : '-') + '</div>'
                    + (failing.length
                        ? '<ul class="text-xs text-red-600 mb-2">'
                            + failing.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('')
                            + '</ul>'
                        : '')
                    + (x.blend_file ? '<div class="text-xs font-mono text-gray-500 mb-2">.blend: '
                        + esc(x.blend_file) + '</div>' : '')
                    + preview
                    + '</div>';
            });
            html += '</div></div>';
            container.innerHTML = html;
            el('sb-compare-back').addEventListener('click', function () {
                renderExpansion();
            });
        } catch (e) {
            container.innerHTML = '<div class="p-3 bg-gray-50 border-t">'
                + '<p class="text-sm text-red-600">Failed to load comparison: '
                + esc((e && e.message) || e) + '</p>'
                + '<button class="btn btn-outline btn-sm mt-2" id="sb-compare-back">Back</button></div>';
            var back = el('sb-compare-back');
            if (back) back.addEventListener('click', function () { renderExpansion(); });
        }
    }

    async function loadTaskRuns() {
        var box = el('sb-runs');
        try {
            box.innerHTML = '<p class="text-sm text-gray-500">Loading history...</p>';
            var r = await fetch('/api/sandbox/runs?limit=1000');
            if (!r.ok) throw new Error('HTTP ' + r.status);
            var j = await r.json();
            historyRuns = j.runs || [];
            var ids = historyRuns.map(function (x) { return x.run_id; });
            if (pinnedRun != null && ids.indexOf(pinnedRun) === -1) pinnedRun = null;
            if (selectedRun != null && ids.indexOf(selectedRun) === -1) selectedRun = null;
            if (expandedModel) {
                var separator = expandedModel.indexOf('::');
                var origin = expandedModel.slice(0, separator);
                var model = expandedModel.slice(separator + 2);
                var stillListed = historyRuns.some(function (x) {
                    return originOf(x) === origin && x.model === model;
                });
                if (!stillListed) {
                    expandedModel = null;
                    openTask = null;
                }
            }
            renderHistory();
        } catch (e) {
            box.innerHTML = '<p class="text-sm text-red-600">Failed to load sandbox runs: '
                + esc((e && e.message) || e) + '</p>'
                + '<button class="btn btn-outline btn-sm mt-2" id="sb-runs-retry">Retry</button>';
            var retry = el('sb-runs-retry');
            if (retry) retry.addEventListener('click', loadTaskRuns);
        }
    }

    var refreshRuns = el('sb-refresh-runs');
    if (refreshRuns) refreshRuns.addEventListener('click', loadTaskRuns);
    loadTaskRuns();
})();
