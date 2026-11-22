// Header status badge poller (pages without their own updater).
// Plain script: dashboard manages its own badge (window.__statusManaged).
(function () {
    async function poll() {
        if (window.__statusManaged) return;
        var el = document.getElementById('lm-status');
        if (!el) return;
        var connected = false;
        try {
            var r = await fetch('/api/status');
            if (r.ok) {
                var j = await r.json();
                connected = !!(j.lm_studio && j.lm_studio.connected);
            }
        } catch (e) {
            connected = false;
        }
        el.className = 'status-badge text-sm font-medium '
            + (connected ? 'status-online' : 'status-offline');
        el.innerHTML = '<span class="status-dot"></span>'
            + (connected ? 'Connected' : 'Disconnected');
    }
    document.addEventListener('DOMContentLoaded', function () {
        // Active-state: highlight the nav link matching the current path.
        try {
            var path = window.location.pathname.replace(/\/+$/, '') || '/';
            document.querySelectorAll('.nav-link').forEach(function (a) {
                var href = (a.getAttribute('href') || '/').replace(/\/+$/, '') || '/';
                var active = href === path
                    || (href !== '/' && path.indexOf(href + '/') === 0)
                    || (href === '/history' && /^\/results\//.test(path))
                    || (href === '/sandbox' && /^\/(sandbox|duels)\//.test(path));
                a.classList.toggle('text-blue-600', active);
                a.classList.toggle('font-semibold', active);
                if (active) a.setAttribute('aria-current', 'page');
                else a.removeAttribute('aria-current');
            });
        } catch (e) { /* nav highlighting is cosmetic */ }
        poll();
        setInterval(poll, 30000);
    });
    poll();
})();
