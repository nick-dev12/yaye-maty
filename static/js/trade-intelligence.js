/* Trade Intelligence — SENEGAL TRADE INTELLIGENCE */

(function () {
    'use strict';

    const app = document.getElementById('trade-intelligence-app');
    if (!app) return;
    // Session test a son propre script (trade-session-test.js)
    if (app.dataset.testMode) return;

    const domainSelect = document.getElementById('ti-domain');
    const durationSelect = document.getElementById('ti-duration');
    const analyzeBtn = document.getElementById('ti-analyze-btn');
    const stopBtn = document.getElementById('ti-stop-btn');
    const progressEl = document.getElementById('ti-progress');
    const progressBar = document.getElementById('ti-progress-bar');
    const progressMsg = document.getElementById('ti-progress-msg');
    const timerEl = document.getElementById('ti-timer');
    const tableBody = document.getElementById('ti-table-body');
    const highlightsEl = document.getElementById('ti-highlights');

    let analysisData = null;
    const analysisScript = document.getElementById('ti-analysis-data');
    if (analysisScript) {
        try {
            analysisData = JSON.parse(analysisScript.textContent);
        } catch (e) {
            analysisData = null;
        }
    }

    let activeTab = 'top_investissement';
    let pollTimer = null;
    let countdownTimer = null;
    let currentTaskId = null;
    let deadlineTs = null;

    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function badgeClass(reco) {
        const t = (reco || '').toLowerCase();
        if (t.includes('éviter') || t.includes('eviter')) return 'ti-badge--avoid';
        if (t.includes('moyen') || t.includes('affaire')) return 'ti-badge--watch';
        return 'ti-badge--buy';
    }

    function scoreClass(note) {
        const n = parseFloat(note) || 0;
        if (n >= 7.5) return 'ti-score--high';
        if (n >= 5) return 'ti-score--mid';
        return 'ti-score--low';
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatRemaining(seconds) {
        const s = Math.max(0, Math.floor(seconds));
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${m}m ${String(r).padStart(2, '0')}s`;
    }

    function productThumbHtml() {
        return (
            '<span class="ti-product-thumb" aria-hidden="true">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">' +
            '<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 8.25h15l-1.1 10.1a1.8 1.8 0 01-1.8 1.6H7.4a1.8 1.8 0 01-1.8-1.6L4.5 8.25z"/>' +
            '<path stroke-linecap="round" stroke-linejoin="round" d="M8.25 8.25V6.6A3.75 3.75 0 0112 2.85 3.75 3.75 0 0115.75 6.6v1.65"/>' +
            '</svg></span>'
        );
    }

    function renderTable(items) {
        if (!items || !items.length) {
            tableBody.innerHTML = '<tr><td colspan="5" class="ti-empty">Aucun produit classé pour cet onglet.</td></tr>';
            return;
        }
        tableBody.innerHTML = items.map((item) => `
            <tr>
                <td data-label="Rang">${item.rang}</td>
                <td data-label="Produit / modèle">
                    <div class="ti-product-cell">
                        ${productThumbHtml()}
                        <span>${escapeHtml(item.produit)}</span>
                    </div>
                </td>
                <td data-label="Note investissement (/10)"><span class="ti-score ${scoreClass(item.note)}">${item.note}</span></td>
                <td data-label="Recommandation"><span class="ti-badge ${badgeClass(item.recommandation)}">${escapeHtml(item.recommandation)}</span></td>
                <td class="ti-synth" data-label="Analyse du marché">${escapeHtml(item.synthese)}</td>
            </tr>
        `).join('');
    }

    function renderHighlights(highlights) {
        if (!highlights) return;
        highlightsEl.hidden = false;
        const set = (prefix, data) => {
            if (!data) return;
            const p = document.getElementById(`ti-hl-${prefix}-product`);
            const s = document.getElementById(`ti-hl-${prefix}-score`);
            const r = document.getElementById(`ti-hl-${prefix}-reco`);
            if (p) p.textContent = data.produit || '—';
            if (s) {
                s.textContent = data.note != null ? `${data.note} / 10` : '—';
                s.className = `ti-score ${scoreClass(data.note)}`;
            }
            if (r) {
                r.textContent = data.recommandation || '—';
                r.className = `ti-badge ${badgeClass(data.recommandation)}`;
            }
        };
        set('top', highlights.top_pick);
        set('growth', highlights.forte_croissance);
        set('margin', highlights.meilleure_marge);
    }

    function applyAnalysis(data) {
        analysisData = data;
        renderHighlights(data.highlights);
        renderTable(data[activeTab] || data.top_investissement || []);
        const title = document.querySelector('.ti-table-title');
        if (title && activeTab === 'top_investissement') {
            title.textContent = "TOP 15 PRODUITS D'INVESTISSEMENT";
        }
    }

    function setProgress(pct, msg) {
        progressEl.hidden = false;
        progressBar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
        progressMsg.textContent = msg || '';
    }

    function startCountdown(remainingSeconds) {
        clearInterval(countdownTimer);
        deadlineTs = Date.now() + (remainingSeconds * 1000);
        const tick = () => {
            const left = Math.max(0, (deadlineTs - Date.now()) / 1000);
            if (timerEl) timerEl.textContent = left > 0 ? `Temps restant : ${formatRemaining(left)}` : 'Durée écoulée — finalisation…';
            if (left <= 0) clearInterval(countdownTimer);
        };
        tick();
        countdownTimer = setInterval(tick, 1000);
    }

    function setRunning(isRunning) {
        analyzeBtn.disabled = isRunning;
        stopBtn.hidden = !isRunning;
        domainSelect.disabled = isRunning;
        durationSelect.disabled = isRunning;
    }

    function pollStatus(taskId) {
        currentTaskId = taskId;
        const urlTemplate = app.dataset.urlStatut;
        const url = urlTemplate.replace('TASK_ID', encodeURIComponent(taskId));

        function tick() {
            fetch(url, { credentials: 'same-origin' })
                .then((r) => r.json())
                .then((data) => {
                    setProgress(data.pourcentage || 0, data.message || '');
                    if (data.state === 'SUCCESS') {
                        clearTimeout(pollTimer);
                        clearInterval(countdownTimer);
                        setRunning(false);
                        currentTaskId = null;
                        if (data.session && data.session.analysis) {
                            applyAnalysis(data.session.analysis);
                        } else if (data.session && data.session.id) {
                            window.location.href = `?session=${data.session.id}`;
                        }
                        return;
                    }
                    if (data.state === 'FAILURE') {
                        clearTimeout(pollTimer);
                        clearInterval(countdownTimer);
                        setRunning(false);
                        currentTaskId = null;
                        progressMsg.textContent = data.message || 'Échec.';
                        return;
                    }
                    pollTimer = setTimeout(tick, 1200);
                })
                .catch(() => {
                    pollTimer = setTimeout(tick, 2000);
                });
        }
        tick();
    }

    function launchAnalysis() {
        const domainSlug = domainSelect.value;
        const duration = parseInt(durationSelect.value, 10) || 20;
        if (!domainSlug) {
            alert('Choisissez un domaine (configuré dans Domaines).');
            return;
        }
        setRunning(true);
        setProgress(2, 'Lancement de la session…');
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
            }),
        })
            .then((r) => r.json())
            .then((data) => {
                if (!data.success) {
                    setRunning(false);
                    clearInterval(countdownTimer);
                    alert(data.error || 'Impossible de lancer l\'analyse.');
                    return;
                }
                pollStatus(data.task_id);
            })
            .catch((err) => {
                setRunning(false);
                clearInterval(countdownTimer);
                alert('Erreur réseau : ' + err.message);
            });
    }

    function stopAnalysis() {
        if (!currentTaskId) return;
        stopBtn.disabled = true;
        setProgress(progressBar.style.width.replace('%', '') || 50, 'Arrêt demandé — analyse en cours…');
        fetch(app.dataset.urlArreter, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ task_id: currentTaskId }),
        })
            .then((r) => r.json())
            .then((data) => {
                if (!data.success) {
                    stopBtn.disabled = false;
                    alert(data.error || 'Arrêt impossible.');
                }
            })
            .catch(() => {
                stopBtn.disabled = false;
            });
    }

    document.querySelectorAll('.ti-tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.ti-tab').forEach((t) => {
                t.classList.remove('is-active');
                t.setAttribute('aria-selected', 'false');
            });
            tab.classList.add('is-active');
            tab.setAttribute('aria-selected', 'true');
            activeTab = tab.dataset.tab;
            if (analysisData) {
                renderTable(analysisData[activeTab] || []);
            }
        });
    });

    analyzeBtn.addEventListener('click', launchAnalysis);
    stopBtn.addEventListener('click', stopAnalysis);

    if (analysisData) {
        applyAnalysis(analysisData);
    }

    const activeTask = app.dataset.activeTask;
    if (activeTask) {
        setRunning(true);
        const rem = parseInt(app.dataset.remaining || '', 10);
        const dur = parseInt(app.dataset.duration || '20', 10);
        startCountdown(Number.isFinite(rem) ? rem : dur * 60);
        pollStatus(activeTask);
    }
})();
