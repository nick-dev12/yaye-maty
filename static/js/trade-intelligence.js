/* Trade Intelligence — SENEGAL TRADE INTELLIGENCE */

(function () {
    'use strict';

    const app = document.getElementById('trade-intelligence-app');
    if (!app) return;
    if (app.dataset.testMode) return;

    const domainPicker = document.getElementById('ti-domain-picker');
    const domainPickerLabel = document.getElementById('ti-domain-picker-label');
    const domainModal = document.getElementById('ti-domain-modal');
    const domainModalBackdrop = document.getElementById('ti-domain-modal-backdrop');
    const domainModalClose = document.getElementById('ti-domain-modal-close');
    const domainModalCancel = document.getElementById('ti-domain-modal-cancel');
    const domainModalConfirm = document.getElementById('ti-domain-modal-confirm');
    const domainSearch = document.getElementById('ti-domain-search');
    const domainSelectAll = document.getElementById('ti-domain-select-all');
    const domainList = document.getElementById('ti-domain-list');
    const domainCountEl = document.getElementById('ti-domain-count');
    const durationSelect = document.getElementById('ti-duration');
    const analyzeBtn = document.getElementById('ti-analyze-btn');
    const stopBtn = document.getElementById('ti-stop-btn');
    const progressEl = document.getElementById('ti-progress');
    const progressBar = document.getElementById('ti-progress-bar');
    const progressMsg = document.getElementById('ti-progress-msg');
    const timerEl = document.getElementById('ti-timer');
    const batchEl = document.getElementById('ti-batch');
    const batchSummary = document.getElementById('ti-batch-summary');
    const batchList = document.getElementById('ti-batch-list');
    const tableBody = document.getElementById('ti-table-body');
    const highlightsEl = document.getElementById('ti-highlights');

    const BATCH_WAVE_SIZE = 3;

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
    let activeTaskIds = [];
    let batchJobs = [];
    let batchCancelled = false;
    let batchDurationSeconds = 0;
    let deadlineTs = null;

    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function domainChecks() {
        return domainList ? Array.from(domainList.querySelectorAll('.ti-domain-check')) : [];
    }

    function visibleChecks() {
        return domainChecks().filter((el) => !el.hidden);
    }

    function selectedSlugs() {
        return domainChecks()
            .filter((el) => {
                const input = el.querySelector('input');
                return input && input.checked;
            })
            .map((el) => el.querySelector('input').value);
    }

    function domainLabelForSlug(slug) {
        const el = domainChecks().find((row) => {
            const input = row.querySelector('input');
            return input && input.value === slug;
        });
        if (!el) return slug;
        const strong = el.querySelector('strong');
        return strong ? strong.textContent.trim() : slug;
    }

    function updateDomainPickerLabel() {
        const slugs = selectedSlugs();
        const total = domainChecks().length;
        if (!domainPickerLabel) return;
        if (!slugs.length) {
            domainPickerLabel.textContent = '— Choisir —';
        } else if (slugs.length === total && total > 1) {
            domainPickerLabel.textContent = `Tous les domaines (${total})`;
        } else if (slugs.length === 1) {
            domainPickerLabel.textContent = domainLabelForSlug(slugs[0]);
        } else {
            domainPickerLabel.textContent = `${slugs.length} domaines sélectionnés`;
        }
        if (domainCountEl) {
            domainCountEl.textContent = total
                ? `${slugs.length} / ${total} domaine${total > 1 ? 's' : ''} sélectionné${slugs.length > 1 ? 's' : ''}`
                : '';
        }
    }

    function openDomainModal() {
        if (!domainModal || !domainPicker || domainPicker.disabled) return;
        domainModal.hidden = false;
        domainModal.classList.remove('is-hidden');
        document.body.classList.add('ti-modal-open');
        updateDomainPickerLabel();
        if (domainSearch) {
            domainSearch.value = '';
            filterDomains('');
            setTimeout(() => domainSearch.focus(), 40);
        }
    }

    function closeDomainModal() {
        if (!domainModal) return;
        domainModal.hidden = true;
        domainModal.classList.add('is-hidden');
        document.body.classList.remove('ti-modal-open');
    }

    function filterDomains(query) {
        const q = (query || '').trim().toLowerCase();
        domainChecks().forEach((el) => {
            const label = el.getAttribute('data-domain-label') || '';
            el.hidden = Boolean(q) && !label.includes(q);
        });
        if (domainSelectAll) {
            const visible = visibleChecks();
            const allOn = visible.length > 0 && visible.every(
                (el) => el.querySelector('input') && el.querySelector('input').checked,
            );
            domainSelectAll.textContent = allOn ? 'Tout désélectionner' : 'Tout sélectionner';
        }
    }

    function toggleSelectAllVisible() {
        const visible = visibleChecks();
        const allOn = visible.length > 0 && visible.every(
            (el) => el.querySelector('input') && el.querySelector('input').checked,
        );
        visible.forEach((el) => {
            const input = el.querySelector('input');
            if (input) input.checked = !allOn;
        });
        updateDomainPickerLabel();
        filterDomains(domainSearch ? domainSearch.value : '');
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

    function jobStateClass(state) {
        if (state === 'SUCCESS') return 'is-done';
        if (state === 'FAILURE') return 'is-failed';
        if (state === 'WAITING') return 'is-waiting';
        return '';
    }

    function jobStatusMessage(job) {
        if (job.state === 'WAITING') return 'En attente';
        if (job.state === 'SUCCESS') return job.message || 'Terminé';
        if (job.state === 'FAILURE') return job.message || 'Échec';
        if (job.timerText) return job.timerText;
        return job.message || 'En cours…';
    }

    function clearJobCountdown(job) {
        if (job.timerInterval) {
            clearInterval(job.timerInterval);
            job.timerInterval = null;
        }
    }

    function startJobCountdown(job) {
        clearJobCountdown(job);
        if (!job.deadlineTs) return;
        const tick = () => {
            const left = Math.max(0, (job.deadlineTs - Date.now()) / 1000);
            if (left > 0) {
                job.timerText = `Temps restant : ${formatRemaining(left)}`;
            } else {
                job.timerText = 'Durée écoulée — finalisation…';
                clearJobCountdown(job);
            }
            renderBatchList();
        };
        tick();
        job.timerInterval = setInterval(tick, 1000);
    }

    function renderBatchList() {
        if (!batchList) return;
        batchList.innerHTML = batchJobs.map((job) => {
            const stateClass = jobStateClass(job.state);
            const viewBtn = job.state === 'SUCCESS' && job.sessionId
                ? `<button type="button" class="ti-batch-view-btn" data-session-id="${job.sessionId}">Voir les résultats</button>`
                : '';
            return `
                <li class="ti-batch-item ${stateClass}" data-slug="${escapeHtml(job.slug || '')}">
                    <div class="ti-batch-item-head">
                        <span class="ti-batch-item-name">${escapeHtml(job.label)}</span>
                        <span class="ti-batch-item-msg">${escapeHtml(jobStatusMessage(job))}</span>
                    </div>
                    <div class="ti-batch-item-bar">
                        <div class="ti-batch-item-bar-fill" style="width:${job.pct || 0}%"></div>
                    </div>
                    ${viewBtn}
                </li>`;
        }).join('');

        batchList.querySelectorAll('.ti-batch-view-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const sid = btn.getAttribute('data-session-id');
                if (sid) window.location.href = `?session=${encodeURIComponent(sid)}`;
            });
        });
    }

    function initBatchQueue(slugs, durationSeconds) {
        batchCancelled = false;
        batchDurationSeconds = durationSeconds;
        batchJobs = slugs.map((slug) => ({
            slug,
            label: domainLabelForSlug(slug),
            taskId: null,
            sessionId: null,
            pct: 0,
            message: 'En attente',
            timerText: '',
            state: 'WAITING',
            analysis: null,
            deadlineTs: null,
            timerInterval: null,
        }));
        if (batchEl) batchEl.hidden = false;
        if (timerEl) timerEl.textContent = '';
        renderBatchList();
        updateBatchSummary();
    }

    function updateBatchSummary() {
        if (!batchSummary || !batchJobs.length) return;
        const done = batchJobs.filter((j) => j.state === 'SUCCESS').length;
        const failed = batchJobs.filter((j) => j.state === 'FAILURE').length;
        const waiting = batchJobs.filter((j) => j.state === 'WAITING').length;
        const running = batchJobs.length - done - failed - waiting;
        batchSummary.textContent = `${done} terminée(s) · ${running} en cours · ${waiting} en attente · ${failed} échec(s)`;
    }

    function syncActiveTaskIds() {
        activeTaskIds = batchJobs
            .filter((j) => j.taskId && j.state !== 'SUCCESS' && j.state !== 'FAILURE' && j.state !== 'WAITING')
            .map((j) => j.taskId);
        currentTaskId = activeTaskIds[0] || null;
    }

    function finishBatchQueue() {
        batchJobs.forEach(clearJobCountdown);
        setRunning(false);
        activeTaskIds = [];
        currentTaskId = null;
        if (timerEl) timerEl.textContent = '';
        const avg = batchJobs.length
            ? Math.round(batchJobs.reduce((acc, j) => acc + (j.pct || 0), 0) / batchJobs.length)
            : 100;
        const done = batchJobs.filter((j) => j.state === 'SUCCESS').length;
        setProgress(avg, `Batch terminé — ${done}/${batchJobs.length} analyse(s) réussie(s).`);
        updateBatchSummary();
        const firstDone = batchJobs.find((j) => j.state === 'SUCCESS' && j.analysis);
        if (firstDone && firstDone.analysis) applyAnalysis(firstDone.analysis);
    }

    function launchSingleDomain(slug, durationMinutes) {
        return fetch(app.dataset.urlLancer, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({
                domain_slug: slug,
                keyword: '',
                duration_minutes: durationMinutes,
            }),
        }).then((r) => r.json());
    }

    function markJobRunning(job) {
        job.state = 'PROGRESS';
        job.deadlineTs = Date.now() + batchDurationSeconds * 1000;
        job.message = 'Collecte en cours…';
        startJobCountdown(job);
        renderBatchList();
        updateBatchSummary();
        syncActiveTaskIds();
    }

    function handleStatusData(data, job) {
        if (job.state === 'WAITING') return;
        job.pct = data.pourcentage || 0;
        if (data.state === 'PROGRESS' || data.state === 'PENDING') {
            if (job.state === 'WAITING') markJobRunning(job);
            else job.state = data.state;
            job.message = data.message || job.message;
        } else {
            job.state = data.state || job.state;
            job.message = data.message || job.message;
        }
        if (data.state === 'SUCCESS') {
            clearJobCountdown(job);
            job.timerText = '';
            job.analysis = data.session && data.session.analysis ? data.session.analysis : null;
            if (data.session && data.session.id) job.sessionId = data.session.id;
        }
        if (data.state === 'FAILURE') {
            clearJobCountdown(job);
            job.timerText = '';
        }
        renderBatchList();
        updateBatchSummary();
        syncActiveTaskIds();
    }

    function pollWaveJobs(waveJobs, onDone) {
        const pending = () => waveJobs.filter(
            (j) => j.state !== 'SUCCESS' && j.state !== 'FAILURE',
        );

        function tick() {
            if (batchCancelled) {
                onDone();
                return;
            }
            const todo = pending();
            if (!todo.length) {
                onDone();
                return;
            }
            Promise.all(todo.map((job) =>
                fetch(statusUrl(job.taskId), { credentials: 'same-origin' })
                    .then((r) => r.json())
                    .then((data) => {
                        handleStatusData(data, job);
                        return data;
                    })
                    .catch(() => null),
            )).then(() => {
                const avg = batchJobs.length
                    ? Math.round(batchJobs.reduce((acc, j) => acc + (j.pct || 0), 0) / batchJobs.length)
                    : 0;
                const active = batchJobs.filter(
                    (j) => j.state !== 'SUCCESS' && j.state !== 'FAILURE' && j.state !== 'WAITING',
                ).length;
                setProgress(avg, active
                    ? `${batchJobs.filter((j) => j.state === 'SUCCESS').length}/${batchJobs.length} terminée(s) — max ${BATCH_WAVE_SIZE} simultanées`
                    : progressMsg.textContent);
                updateBatchSummary();
                if (pending().length) pollTimer = setTimeout(tick, 1500);
                else onDone();
            });
        }
        tick();
    }

    function processNextWave(durationMinutes) {
        if (batchCancelled) {
            finishBatchQueue();
            return;
        }
        const waiting = batchJobs.filter((j) => j.state === 'WAITING');
        if (!waiting.length) {
            finishBatchQueue();
            return;
        }
        const wave = waiting.slice(0, BATCH_WAVE_SIZE);
        setProgress(
            Math.round(batchJobs.reduce((acc, j) => acc + (j.pct || 0), 0) / batchJobs.length),
            `Lancement de ${wave.length} analyse(s) (${batchJobs.filter((j) => j.state === 'WAITING').length} en attente)…`,
        );

        Promise.all(wave.map((job) =>
            launchSingleDomain(job.slug, durationMinutes)
                .then((data) => {
                    if (!data.success) {
                        job.state = 'FAILURE';
                        job.message = data.error || 'Échec au lancement.';
                        return;
                    }
                    job.taskId = data.task_id;
                    job.sessionId = data.session_id;
                    markJobRunning(job);
                })
                .catch((err) => {
                    job.state = 'FAILURE';
                    job.message = `Erreur réseau : ${err.message}`;
                }),
        )).then(() => {
            renderBatchList();
            updateBatchSummary();
            syncActiveTaskIds();
            const runnable = wave.filter(
                (j) => j.taskId && j.state !== 'FAILURE',
            );
            if (!runnable.length) {
                processNextWave(durationMinutes);
                return;
            }
            pollWaveJobs(runnable, () => {
                if (!batchCancelled) processNextWave(durationMinutes);
                else finishBatchQueue();
            });
        });
    }

    function startBatchQueue(slugs, durationMinutes) {
        initBatchQueue(slugs, durationMinutes * 60);
        setRunning(true);
        if (timerEl) timerEl.textContent = '';
        setProgress(2, `File : ${slugs.length} domaine(s) — ${BATCH_WAVE_SIZE} max simultanées`);
        processNextWave(durationMinutes);
    }

    function startCountdown(remainingSeconds) {
        clearInterval(countdownTimer);
        deadlineTs = Date.now() + (remainingSeconds * 1000);
        const tick = () => {
            const left = Math.max(0, (deadlineTs - Date.now()) / 1000);
            if (timerEl) {
                timerEl.textContent = left > 0
                    ? `Temps restant : ${formatRemaining(left)}`
                    : 'Durée écoulée — finalisation…';
            }
            if (left <= 0) clearInterval(countdownTimer);
        };
        tick();
        countdownTimer = setInterval(tick, 1000);
    }

    function setRunning(isRunning) {
        analyzeBtn.disabled = isRunning;
        stopBtn.hidden = !isRunning;
        if (domainPicker) domainPicker.disabled = isRunning;
        durationSelect.disabled = isRunning;
    }

    function statusUrl(taskId) {
        return app.dataset.urlStatut.replace('TASK_ID', encodeURIComponent(taskId));
    }

    function pollStatus(taskId) {
        currentTaskId = taskId;
        activeTaskIds = [taskId];

        function tick() {
            fetch(statusUrl(taskId), { credentials: 'same-origin' })
                .then((r) => r.json())
                .then((data) => {
                    setProgress(data.pourcentage || 0, data.message || '');
                    if (data.state === 'SUCCESS') {
                        clearTimeout(pollTimer);
                        clearInterval(countdownTimer);
                        setRunning(false);
                        currentTaskId = null;
                        activeTaskIds = [];
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
                        activeTaskIds = [];
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
        const slugs = selectedSlugs();
        const duration = parseInt(durationSelect.value, 10) || 20;
        if (!slugs.length) {
            openDomainModal();
            return;
        }
        if (slugs.length > 1) {
            startBatchQueue(slugs, duration);
            return;
        }
        setRunning(true);
        setProgress(2, 'Lancement de la session…');
        startCountdown(duration * 60);

        launchSingleDomain(slugs[0], duration)
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
        batchCancelled = true;
        clearTimeout(pollTimer);
        const ids = activeTaskIds.length ? activeTaskIds : (currentTaskId ? [currentTaskId] : []);
        if (!ids.length) {
            finishBatchQueue();
            return;
        }
        stopBtn.disabled = true;
        setProgress(progressBar.style.width.replace('%', '') || 50, 'Arrêt demandé — analyse en cours…');

        Promise.all(ids.map((taskId) =>
            fetch(app.dataset.urlArreter, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ task_id: taskId }),
            }).then((r) => r.json()),
        )).then((results) => {
            const failed = results.find((r) => r && !r.success);
            if (failed) {
                stopBtn.disabled = false;
                alert(failed.error || 'Arrêt impossible.');
            }
        }).catch(() => {
            stopBtn.disabled = false;
        });
    }

    if (domainPicker) domainPicker.addEventListener('click', openDomainModal);
    if (domainModalClose) domainModalClose.addEventListener('click', closeDomainModal);
    if (domainModalCancel) domainModalCancel.addEventListener('click', closeDomainModal);
    if (domainModalBackdrop) domainModalBackdrop.addEventListener('click', closeDomainModal);
    if (domainModalConfirm) {
        domainModalConfirm.addEventListener('click', () => {
            if (!selectedSlugs().length) {
                alert('Sélectionnez au moins un domaine.');
                return;
            }
            updateDomainPickerLabel();
            closeDomainModal();
        });
    }
    if (domainSelectAll) domainSelectAll.addEventListener('click', toggleSelectAllVisible);
    if (domainSearch) {
        domainSearch.addEventListener('input', (e) => filterDomains(e.target.value));
    }
    domainChecks().forEach((el) => {
        const input = el.querySelector('input');
        if (input) input.addEventListener('change', updateDomainPickerLabel);
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && domainModal && !domainModal.hidden) closeDomainModal();
    });

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

    updateDomainPickerLabel();

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
