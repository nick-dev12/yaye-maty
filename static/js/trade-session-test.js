/* Session test — lance une source unique via Trade Intelligence API */

(function () {
    'use strict';

    const app = document.getElementById('trade-intelligence-app');
    if (!app || !app.dataset.testMode) return;

    const domainSelect = document.getElementById('ti-domain');
    const durationSelect = document.getElementById('ti-duration');
    const stopBtn = document.getElementById('ti-stop-btn');
    const progressEl = document.getElementById('ti-progress');
    const progressBar = document.getElementById('ti-progress-bar');
    const progressMsg = document.getElementById('ti-progress-msg');
    const timerEl = document.getElementById('ti-timer');
    const tableBody = document.getElementById('ti-table-body');
    const sourceBtns = document.querySelectorAll('.ti-source-btn');

    let pollTimer = null;
    let countdownTimer = null;
    let currentTaskId = null;
    let deadlineTs = null;

    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function formatRemaining(seconds) {
        const s = Math.max(0, Math.floor(seconds));
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${m}m ${String(r).padStart(2, '0')}s`;
    }

    function setRunning(isRunning) {
        sourceBtns.forEach((b) => { b.disabled = isRunning; });
        if (stopBtn) stopBtn.hidden = !isRunning;
        if (domainSelect) domainSelect.disabled = isRunning;
        if (durationSelect) durationSelect.disabled = isRunning;
    }

    function setProgress(pct, msg) {
        if (!progressEl) return;
        progressEl.hidden = false;
        progressBar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
        progressMsg.textContent = msg || '';
    }

    function startCountdown(remainingSeconds) {
        clearInterval(countdownTimer);
        deadlineTs = Date.now() + remainingSeconds * 1000;
        const tick = () => {
            const left = Math.max(0, (deadlineTs - Date.now()) / 1000);
            if (timerEl) timerEl.textContent = left > 0 ? `Temps restant : ${formatRemaining(left)}` : 'Durée écoulée…';
            if (left <= 0) clearInterval(countdownTimer);
        };
        tick();
        countdownTimer = setInterval(tick, 1000);
    }

    function renderTop(items) {
        if (!tableBody) return;
        if (!items || !items.length) {
            tableBody.innerHTML = '<tr><td colspan="5" class="ti-empty">Aucun résultat.</td></tr>';
            return;
        }
        tableBody.innerHTML = items.map((item) => `
            <tr>
                <td data-label="Rang">${item.rang}</td>
                <td data-label="Produit">${item.produit || ''}</td>
                <td data-label="Note">${item.note}</td>
                <td data-label="Recommandation">${item.recommandation || ''}</td>
                <td class="ti-synth" data-label="Analyse du marché">${item.synthese || ''}</td>
            </tr>
        `).join('');
    }

    function pollStatus(taskId) {
        currentTaskId = taskId;
        const url = app.dataset.urlStatut.replace('TASK_ID', encodeURIComponent(taskId));
        function tick() {
            fetch(url, { credentials: 'same-origin' })
                .then((r) => r.json())
                .then((data) => {
                    setProgress(data.pourcentage || 0, data.message || '');
                    if (data.state === 'SUCCESS' || data.state === 'FAILURE') {
                        clearTimeout(pollTimer);
                        clearInterval(countdownTimer);
                        setRunning(false);
                        currentTaskId = null;
                        if (data.session && data.session.analysis) {
                            renderTop(data.session.analysis.top_investissement || []);
                        } else if (data.session && data.session.id) {
                            window.location.href = `?session=${data.session.id}`;
                        }
                        return;
                    }
                    pollTimer = setTimeout(tick, 1200);
                })
                .catch(() => { pollTimer = setTimeout(tick, 2000); });
        }
        tick();
    }

    function launchSource(source) {
        const domainSlug = domainSelect.value;
        const duration = parseInt(durationSelect.value, 10) || 10;
        if (!domainSlug) { alert('Choisissez un domaine.'); return; }

        setRunning(true);
        setProgress(2, `Test ${source}…`);
        startCountdown(duration * 60);

        fetch(app.dataset.urlLancer, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({
                domain_slug: domainSlug,
                keyword: '',
                duration_minutes: duration,
                sources: [source],
            }),
        })
            .then((r) => r.json())
            .then((data) => {
                if (!data.success) {
                    setRunning(false);
                    clearInterval(countdownTimer);
                    alert(data.error || 'Échec lancement.');
                    return;
                }
                pollStatus(data.task_id);
            })
            .catch((err) => {
                setRunning(false);
                clearInterval(countdownTimer);
                alert(err.message);
            });
    }

    sourceBtns.forEach((btn) => {
        btn.addEventListener('click', () => launchSource(btn.dataset.source));
    });

    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            if (!currentTaskId) return;
            stopBtn.disabled = true;
            fetch(app.dataset.urlArreter, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ task_id: currentTaskId }),
            }).finally(() => { stopBtn.disabled = false; });
        });
    }

    if (app.dataset.activeTask) {
        setRunning(true);
        const dur = parseInt(app.dataset.duration || '10', 10);
        startCountdown(dur * 60);
        pollStatus(app.dataset.activeTask);
    }
})();
