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

    function renderHistory() {
        var box = el('sb-runs');
        if (!historyRuns.length) {
            box.innerHTML = '<p class="text-sm text-gray-500">No sandbox task runs yet. Run one with '
                + '<code>python -m lm_optimizer.cli.main lab sandbox --task company_website --model &lt;model&gt;</code></p>';
            return;
        }
        var groups = groupRuns(historyRuns);
        box.innerHTML = '<p class="text-xs text-gray-500 mb-2">' + historyRuns.length + ' run(s), '
            + groups.length + ' model(s). Click a model to see its tests.</p>'
            + '<div class="table-container"><table class="table"><thead><tr>'
            + '<th>Model</th><th>Runs</th><th>Tasks</th><th>Best</th><th>Last run</th><th></th>'
            + '</tr></thead><tbody>'
            + groups.map(function (g) {
                var tasks = {};
                g.runs.forEach(function (r) { tasks[r.run.task] = true; });
                var taskCount = Object.keys(tasks).length;
                return '<tr class="history-model" data-model="' + esc(g.model) + '">'
                    + '<td class="font-mono text-xs">' + esc(g.model) + '</td>'
                    + '<td class="font-mono">' + g.runs.length + '</td>'
                    + '<td class="font-mono">' + taskCount + '</td>'
                    + '<td>' + (g.best == null ? '-' : scoreText({ final_score: g.best }) + ' <span class="text-xs text-gray-500">' + esc(g.bestTask) + '</span>') + '</td>'
                    + '<td class="font-mono text-xs">' + esc(g.last || '') + '</td>'
                    + '<td><button class="btn btn-outline btn-sm view-model-runs" data-model="' + esc(g.model) + '">View</button></td>'
                    + '</tr>';
            }).join('')
            + '</tbody></table></div><div id="sb-model-detail" class="mt-4"></div>';

        Array.prototype.forEach.call(box.querySelectorAll('.view-model-runs'), function (button) {
            button.addEventListener('click', function (event) {
                event.stopPropagation();
                showModelRuns(button.dataset.model);
            });
        });
        Array.prototype.forEach.call(box.querySelectorAll('tr.history-model'), function (row) {
            row.addEventListener('click', function () { showModelRuns(row.dataset.model); });
        });
    }

    function pinLabel(index) {
        if (pinnedRun == null) return 'Pin';
        return pinnedRun === Number(index) ? 'Pinned' : 'Pin';
    }

    function showModelRuns(model) {
        var panel = el('sb-model-detail');
        var runs = historyRuns.map(function (x, idx) { return { index: idx, run: x }; })
            .filter(function (r) { return (r.run.model || 'unknown') === model; });
        if (!runs.length) return;

        var tasks = {};
        runs.forEach(function (r) {
            var t = r.run.task || 'unknown';
            if (!tasks[t]) tasks[t] = [];
            tasks[t].push(r);
        });
        var taskNames = Object.keys(tasks).sort();

        var html = '<div class="card"><div class="card-header"><div class="flex items-center justify-between">'
            + '<h3 class="font-bold">' + esc(model) + '</h3>'
            + '<button class="btn btn-outline btn-sm" id="sb-model-close">Close</button>'
            + '</div><p class="text-xs text-gray-500 mt-1">' + runs.length + ' run(s) across '
            + taskNames.length + ' test(s), newest first.</p></div><div class="card-body space-y-4">';

        taskNames.forEach(function (task) {
            var list = tasks[task].slice().sort(function (a, b) {
                return (b.run.ts || '').localeCompare(a.run.ts || '');
            });
            var best = null;
            list.forEach(function (r) {
                if (r.run.final_score != null && (best == null || r.run.final_score > best)) {
                    best = r.run.final_score;
                }
            });
            html += '<div><div class="flex items-center justify-between mb-1">'
                + '<h4 class="font-semibold">' + esc(task) + '</h4>'
                + '<span class="text-xs text-gray-500">' + list.length + ' run(s), best '
                + (best == null ? '-' : best.toFixed(2)) + '</span></div>'
                + '<div class="table-container"><table class="table"><tbody>'
                + list.map(function (r) {
                    var x = r.run;
                    var cmpBtn = (pinnedRun != null && pinnedRun !== r.index)
                        ? '<button class="btn btn-outline btn-sm compare-run" data-a="' + pinnedRun + '" data-b="' + r.index + '">Compare</button> '
                        : '';
                    return '<tr>'
                        + '<td class="font-mono text-xs">' + esc(x.ts || '') + '</td>'
                        + '<td>' + resultBadge(x) + '</td>'
                        + '<td class="font-mono">' + scoreText(x) + '</td>'
                        + '<td class="font-mono text-xs">' + (x.duration_s ? Number(x.duration_s).toFixed(0) + 's' : '-') + '</td>'
                        + '<td class="text-right space-x-1">'
                        + '<button class="btn btn-outline btn-sm open-run" data-index="' + r.index + '">Open</button>'
                        + '<button class="btn btn-outline btn-sm pin-run" data-index="' + r.index + '">' + pinLabel(r.index) + '</button>'
                        + cmpBtn
                        + '</td>'
                        + '</tr>';
                }).join('')
                + '</tbody></table></div></div>';
        });
        html += '</div></div>';
        panel.innerHTML = html;

        el('sb-model-close').addEventListener('click', function () {
            panel.innerHTML = '';
            pinnedRun = null;
        });
        Array.prototype.forEach.call(panel.querySelectorAll('.open-run'), function (button) {
            button.addEventListener('click', function () {
                showSandboxRunDetail(button.dataset.index, model);
            });
        });
        Array.prototype.forEach.call(panel.querySelectorAll('.pin-run'), function (button) {
            button.addEventListener('click', function () {
                pinnedRun = (pinnedRun === Number(button.dataset.index)) ? null : Number(button.dataset.index);
                showModelRuns(model);
            });
        });
        Array.prototype.forEach.call(panel.querySelectorAll('.compare-run'), function (button) {
            button.addEventListener('click', function () {
                showCompareRuns(button.dataset.a, button.dataset.b);
            });
        });
    }

    async function showSandboxRunDetail(index, model) {
        var panel = el('sb-model-detail');
        try {
            var r = await fetch('/api/sandbox/run/' + encodeURIComponent(index));
            if (!r.ok) throw new Error('HTTP ' + r.status);
            var x = await r.json();
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
                : '';
            var blend = x.blend_file
                ? '<tr><td class="font-bold">Blend file</td><td class="font-mono text-xs">' + esc(x.blend_file)
                    + '<div class="text-gray-500">Open it directly in Blender.</div></td></tr>'
                : '';

            panel.innerHTML = '<div class="card"><div class="card-body">'
                + '<div class="flex items-center justify-between mb-2">'
                + '<h3 class="font-bold text-lg">Run detail</h3>'
                + '<button class="btn btn-outline btn-sm" id="sb-run-back">Back</button>'
                + '</div>'
                + '<table class="table text-sm"><tbody>'
                + '<tr><td class="font-bold">Time</td><td>' + esc(x.ts || '') + '</td></tr>'
                + '<tr><td class="font-bold">Model</td><td class="font-mono">' + esc(x.model || '') + '</td></tr>'
                + '<tr><td class="font-bold">Task</td><td>' + esc(x.task || '') + '</td></tr>'
                + '<tr><td class="font-bold">Score</td><td class="font-mono">' + scoreText(x) + '</td></tr>'
                + '<tr><td class="font-bold">Result</td><td>' + resultBadge(x) + '</td></tr>'
                + '<tr><td class="font-bold">Status</td><td>' + esc(x.status || 'measured') + '</td></tr>'
                + '<tr><td class="font-bold">Repairs</td><td>' + (x.repair_count || 0) + '</td></tr>'
                + '<tr><td class="font-bold">Duration</td><td class="font-mono">' + (x.duration_s ? Number(x.duration_s).toFixed(0) + 's' : '-') + '</td></tr>'
                + '<tr><td class="font-bold">Workdir</td><td class="font-mono text-xs truncate" title="' + esc(x.workdir || '') + '">' + esc(x.workdir || '') + '</td></tr>'
                + blend
                + '<tr><td class="font-bold">Failing checks</td><td>' + failingHtml + '</td></tr>'
                + (crit ? '<tr><td class="font-bold">Critical failures</td><td>' + crit + '</td></tr>' : '')
                + (artifacts ? '<tr><td class="font-bold">Artifacts</td><td>' + artifacts + '</td></tr>' : '')
                + (x.error ? '<tr><td class="font-bold">Error</td><td class="text-red-600 text-xs">' + esc(x.error) + '</td></tr>' : '')
                + '</tbody></table>'
                + '<div class="mt-4"><h4 class="font-bold">Preview</h4>'
                + (x.artifacts || []).map(function (a) {
                    var rel = x.workdir ? x.workdir.replace(/^results[\\/]sandbox[\\/]/, '') + '/' + a : a;
                    var safeRel = rel.replace(/\\/g, '/');
                    if (/[.](html|htm)$/i.test(a)) {
                        return '<div class="mt-2 border rounded bg-black p-1">'
                            + '<iframe sandbox="" src="/sandbox/files?path=' + encodeURIComponent(safeRel) + '"'
                            + ' class="w-full border rounded" style="height:520px" title="' + esc(a) + ' preview"></iframe>'
                            + '</div>';
                    }
                    if (/[.](py|js|txt|json|md)$/i.test(a)) {
                        return '<details class="mt-2"><summary class="text-sm font-semibold cursor-pointer">'
                            + esc(a) + '</summary>'
                            + '<iframe src="/sandbox/files?path=' + encodeURIComponent(safeRel) + '"'
                            + ' class="w-full border rounded" style="height:320px" title="' + esc(a) + ' preview"></iframe>'
                            + '</details>';
                    }
                    return '<p class="text-xs text-gray-500 mt-2">' + esc(a) + '</p>';
                }).join('')
                + '</div></div></div>';

            el('sb-run-back').addEventListener('click', function () {
                if (model) showModelRuns(model); else renderHistory();
            });
        } catch (e) {
            panel.innerHTML = '<p class="text-sm text-red-600">Failed to load run detail: '
                + esc((e && e.message) || e) + '</p>';
        }
    }

    async function showCompareRuns(indexA, indexB) {
        var panel = el('sb-model-detail');
        panel.innerHTML = '<p class="text-sm text-gray-500">Loading comparison...</p>';
        try {
            var responses = await Promise.all([
                fetch('/api/sandbox/run/' + encodeURIComponent(indexA)),
                fetch('/api/sandbox/run/' + encodeURIComponent(indexB)),
            ]);
            if (!responses[0].ok || !responses[1].ok) throw new Error('HTTP ' + (responses[0].ok ? responses[1].status : responses[0].status));
            var runs = await Promise.all(responses.map(function (r) { return r.json(); }));
            var html = '<div class="card"><div class="card-header"><div class="flex items-center justify-between">'
                + '<h3 class="font-bold">Compare two runs</h3>'
                + '<button class="btn btn-outline btn-sm" id="sb-compare-close">Close</button>'
                + '</div></div><div class="card-body grid md:grid-cols-2 gap-4">';
            runs.forEach(function (x) {
                var failing = [];
                (x.attempts || []).forEach(function (a) {
                    (a.failing_checks || []).forEach(function (f) { failing.push(f); });
                });
                failing = failing.filter(function (v, i, arr) { return arr.indexOf(v) === i; });
                var preview = (x.artifacts || []).map(function (a) {
                    var rel = x.workdir ? x.workdir.replace(/^results[\\/]sandbox[\\/]/, '') + '/' + a : a;
                    var safeRel = rel.replace(/\\/g, '/');
                    if (/[.](html|htm)$/i.test(a)) {
                        return '<div class="mt-2 border rounded bg-black p-1">'
                            + '<iframe sandbox="" src="/sandbox/files?path=' + encodeURIComponent(safeRel) + '"'
                            + ' class="w-full border rounded" style="height:260px" title="' + esc(a) + ' preview"></iframe>'
                            + '</div>';
                    }
                    if (/[.](py|js|txt|json|md)$/i.test(a)) {
                        return '<details class="mt-2" open><summary class="text-sm font-semibold cursor-pointer">' + esc(a) + '</summary>'
                            + '<iframe src="/sandbox/files?path=' + encodeURIComponent(safeRel) + '"'
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
                    + (failing.length ? '<ul class="text-xs text-red-600 mb-2">' + failing.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('') + '</ul>' : '')
                    + (x.blend_file ? '<div class="text-xs font-mono text-gray-500 mb-2">.blend: ' + esc(x.blend_file) + '</div>' : '')
                    + preview
                    + '</div>';
            });
            html += '</div></div>';
            panel.innerHTML = html;
            el('sb-compare-close').addEventListener('click', function () { panel.innerHTML = ''; });
        } catch (e) {
            panel.innerHTML = '<p class="text-sm text-red-600">Failed to load comparison: '
                + esc((e && e.message) || e) + '</p>';
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
            renderHistory();
        } catch (e) {
            box.innerHTML = '<p class="text-sm text-red-600">Failed to load sandbox runs: '
                + esc((e && e.message) || e) + '</p>';
        }
    }

    var refreshRuns = el('sb-refresh-runs');
    if (refreshRuns) refreshRuns.addEventListener('click', loadTaskRuns);
    loadTaskRuns();
})();
