/**
 * Collecte manuelle — zones test/prod, session Django, polling Celery
 */
(function () {
    'use strict';

    const app = document.getElementById('collecte-app');
    if (!app) return;

    const urlLancer = app.dataset.urlLancer;
    const urlStatutTemplate = app.dataset.urlStatut;
    const urlArreter = app.dataset.urlArreter;
    const urlReset = app.dataset.urlReset || '';
    const urlIntelligence = app.dataset.urlIntelligence || '/intelligence/';
    const jobKeyword = app.dataset.jobKeyword || 'keyword';
    const sessionMinutes = parseInt(app.dataset.sessionMinutes, 10) || 20;

    function createZone(name, isTest) {
        return {
            name: name,
            isTest: isTest,
            progressPanel: document.getElementById('collecte-progress-panel-' + name),
            progressLabel: document.getElementById('collecte-progress-label-' + name),
            resultPanel: document.getElementById('collecte-result-panel-' + name),
            statutTexte: document.getElementById('collecte-statut-texte-' + name),
            progressBar: document.getElementById('collecte-barre-progression-' + name),
            progressPct: document.getElementById('collecte-progress-pct-' + name),
            progressTrack: document.getElementById('collecte-progress-track-' + name),
            progressHint: document.getElementById('collecte-progress-hint-' + name),
            stopBtn: document.getElementById('collecte-stop-btn-' + name),
            resetBtn: document.getElementById('collecte-reset-btn-' + name),
            resultText: document.getElementById('collecte-result-text-' + name),
        };
    }

    const zones = {
        test: createZone('test', true),
        prod: createZone('prod', false),
    };

    const testTimerEl = document.getElementById('collecte-test-timer');
    const testTimerValue = document.getElementById('collecte-test-timer-value');
    const keywordSelect = document.getElementById('collecte-keyword-select');
    const keywordBtn = document.getElementById('collecte-keyword-btn');
    const testKeywordSelect = document.getElementById('collecte-test-keyword-select');
    const testKeywordBtn = document.getElementById('collecte-test-keyword-btn');

    let pollingTimer = null;
    let timerInterval = null;
    let timerEndsAt = null;
    let isRunning = false;
    let currentTaskId = null;
    let activeZone = null;
    let currentPhase = 'collecte';
    let stopRequested = false;

    function getCsrfToken() {
        const input = app.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) return input.value;
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function statutUrl(taskId) {
        return urlStatutTemplate.replace('00000000-0000-0000-0000-000000000000', taskId);
    }

    function setRunning(running) {
        isRunning = running;
        app.querySelectorAll('.collecte-job-btn, .collecte-keyword-btn, .collecte-test-btn, .collecte-test-keyword-btn').forEach(function (btn) {
            btn.disabled = running;
        });
        app.querySelectorAll('.collecte-job').forEach(function (card) {
            card.classList.toggle('is-running', running);
        });
    }

    function hideZonePanelsExcept(zone) {
        Object.keys(zones).forEach(function (key) {
            const z = zones[key];
            if (!z.progressPanel || !z.resultPanel) return;
            if (zone && z.name === zone.name) return;
            z.progressPanel.hidden = true;
            z.resultPanel.hidden = true;
            z.progressPanel.classList.remove('is-error');
        });
    }

    function resetTestTimerDisplay() {
        if (testTimerValue) testTimerValue.textContent = sessionMinutes + ':00';
    }

    function stopTestTimer() {
        if (timerInterval) {
            window.clearInterval(timerInterval);
            timerInterval = null;
        }
        timerEndsAt = null;
        resetTestTimerDisplay();
        if (testTimerEl) testTimerEl.classList.remove('is-active');
    }

    function startTestTimer() {
        stopTestTimer();
        timerEndsAt = Date.now() + sessionMinutes * 60 * 1000;
        if (testTimerEl) testTimerEl.classList.add('is-active');

        function tick() {
            if (!timerEndsAt) return;
            const remaining = Math.max(0, timerEndsAt - Date.now());
            const mins = Math.floor(remaining / 60000);
            const secs = Math.floor((remaining % 60000) / 1000);
            if (testTimerValue) {
                testTimerValue.textContent = mins + ':' + String(secs).padStart(2, '0');
            }
            if (remaining <= 0) stopTestTimer();
        }

        tick();
        timerInterval = window.setInterval(tick, 1000);
    }

    function setPhase(zone, phase) {
        currentPhase = phase || 'collecte';
        if (!zone || !zone.progressPanel) return;

        zone.progressPanel.classList.toggle('collecte-progress-panel--nlp', currentPhase === 'nlp');
        zone.progressPanel.classList.toggle(
            'collecte-progress-panel--test-mode',
            zone.isTest && currentPhase !== 'done'
        );

        if (currentPhase === 'nlp') {
            zone.progressLabel.textContent = zone.isTest ? 'Test — analyse hybride' : 'Analyse hybride en cours';
        } else {
            zone.progressLabel.textContent = zone.isTest ? 'Test — collecte en cours' : 'Collecte en cours';
        }
    }

    function updateProgress(zone, pct, message, phase, canStop) {
        if (!zone) return;
        const value = Math.max(0, Math.min(100, Number(pct) || 0));

        if (phase && phase !== currentPhase) {
            setPhase(zone, phase);
            if (phase === 'nlp' && zone.progressBar) {
                zone.progressBar.style.transition = 'none';
                zone.progressBar.style.width = '0%';
                if (zone.progressPct) zone.progressPct.textContent = '0%';
                window.requestAnimationFrame(function () {
                    zone.progressBar.style.transition = '';
                });
            }
        }

        if (zone.progressBar) zone.progressBar.style.width = value + '%';
        if (zone.progressPct) zone.progressPct.textContent = value + '%';
        if (zone.progressTrack) zone.progressTrack.setAttribute('aria-valuenow', String(value));
        if (zone.statutTexte) zone.statutTexte.textContent = message || 'Collecte en cours…';

        if (zone.stopBtn) {
            zone.stopBtn.hidden = !canStop || stopRequested;
            if (canStop && currentPhase === 'nlp') {
                zone.stopBtn.textContent = 'Arrêter l’analyse';
            }
        }
    }

    function showProgress(zone, resume) {
        if (!zone || !zone.progressPanel) return;
        hideZonePanelsExcept(zone);
        zone.resultPanel.hidden = true;
        zone.progressPanel.hidden = false;
        zone.progressPanel.classList.remove('is-error');
        setPhase(zone, 'collecte');
        zone.progressPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        if (resume && zone.statutTexte) {
            zone.statutTexte.textContent = 'Reprise du suivi après actualisation…';
        }
    }

    function showSuccess(zone, message, count) {
        if (!zone) return;
        zone.progressPanel.hidden = true;
        zone.resultPanel.hidden = false;
        const suffix = typeof count === 'number' ? ' — ' + count + ' élément(s) traité(s).' : '.';
        if (zone.resultText) zone.resultText.textContent = message + suffix;
        if (zone.isTest) stopTestTimer();
        setRunning(false);
        currentTaskId = null;
        activeZone = null;
    }

    function showFailure(zone, message) {
        if (!zone) return;
        if (pollingTimer) {
            window.clearTimeout(pollingTimer);
            pollingTimer = null;
        }
        zone.progressPanel.hidden = false;
        zone.resultPanel.hidden = true;
        zone.progressPanel.classList.add('is-error');
        let text = message || 'Échec de la collecte.';
        if (text.indexOf('test_mode') !== -1 || text.indexOf('unexpected keyword') !== -1) {
            text = 'Worker Celery obsolète — Ctrl+C puis .\\scripts\\run_celery_worker.ps1';
        }
        updateProgress(zone, 0, text, 'collecte', false);
        if (zone.stopBtn) zone.stopBtn.hidden = true;
        if (zone.resetBtn) {
            zone.resetBtn.hidden = false;
            zone.resetBtn.disabled = false;
            zone.resetBtn.textContent = 'Libérer / fermer';
        }
        if (zone.isTest) stopTestTimer();
        setRunning(false);
        currentTaskId = null;
        activeZone = zone;
        zone.progressPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function dismissProgress(zone) {
        if (!zone) return;
        if (pollingTimer) {
            window.clearTimeout(pollingTimer);
            pollingTimer = null;
        }
        zone.progressPanel.hidden = true;
        zone.resultPanel.hidden = true;
        zone.progressPanel.classList.remove('is-error');
        if (zone.stopBtn) zone.stopBtn.hidden = true;
        if (zone.resetBtn) zone.resetBtn.hidden = true;
        setRunning(false);
        currentTaskId = null;
        activeZone = null;
        stopRequested = false;
        if (zone.isTest) stopTestTimer();
    }

    function handleStatutData(data) {
        const zone = activeZone;
        if (!zone) return;

        const etat = data.etat;
        const phase = data.phase || 'collecte';
        const canStop = Boolean(data.can_stop);

        if (data.test_mode !== undefined && zone.isTest !== Boolean(data.test_mode)) {
            /* ignore stale poll */
        }

        if (etat === 'PROGRESS' || etat === 'PENDING') {
            const stopLabel = etat === 'PENDING' ? 'Annuler l’attente' : 'Arrêter et analyser';
            if (zone.stopBtn && !stopRequested) {
                zone.stopBtn.textContent = stopLabel;
                zone.stopBtn.hidden = false;
            }
            if (zone.resetBtn) {
                // Toujours disponible pendant un run (PENDING ou PROGRESS) pour débloquer.
                zone.resetBtn.hidden = false;
                zone.resetBtn.disabled = false;
            }
            updateProgress(zone, data.pourcentage || 0, data.message, phase, canStop || etat === 'PENDING');
            pollingTimer = window.setTimeout(function () {
                verifierStatut(currentTaskId);
            }, 1000);
            return;
        }

        if (etat === 'SUCCESS') {
            updateProgress(zone, 100, data.message, phase === 'done' ? 'nlp' : phase, false);
            if (data.cancelled) {
                if (zone.statutTexte) {
                    zone.statutTexte.textContent =
                        'Arrêt terminé — données partielles traitées. Ouverture des résultats…';
                }
                window.setTimeout(function () {
                    window.location.href = urlIntelligence;
                }, 1200);
                return;
            }
            if (zone.isTest && (phase === 'done' || data.phase === 'done')) {
                window.setTimeout(function () {
                    window.location.href = urlIntelligence;
                }, 700);
                return;
            }
            window.setTimeout(function () {
                showSuccess(zone, data.message || 'Terminé avec succès', data.resultats);
            }, 400);
            return;
        }

        if (etat === 'FAILURE') {
            showFailure(zone, data.message);
            return;
        }

        updateProgress(zone, data.pourcentage || 0, data.message || 'En attente…', phase, canStop);
        pollingTimer = window.setTimeout(function () {
            verifierStatut(currentTaskId);
        }, 1000);
    }

    function verifierStatut(taskId) {
        if (!taskId || !activeZone) return;

        fetch(statutUrl(taskId), {
            method: 'GET',
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
        })
            .then(function (response) {
                if (!response.ok) throw new Error('Impossible de lire le statut.');
                return response.json();
            })
            .then(handleStatutData)
            .catch(function () {
                showFailure(activeZone, 'Erreur réseau lors du suivi de la tâche.');
            });
    }

    function resumeTask(taskId, testMode) {
        activeZone = testMode ? zones.test : zones.prod;
        isRunning = true;
        currentTaskId = taskId;
        stopRequested = false;
        setRunning(true);
        showProgress(activeZone, true);
        if (testMode) startTestTimer();
        verifierStatut(taskId);
    }

    function demarrerCollecte(job, keywordId, testMode) {
        if (isRunning) return;

        if (pollingTimer) {
            window.clearTimeout(pollingTimer);
            pollingTimer = null;
        }

        activeZone = testMode ? zones.test : zones.prod;
        currentTaskId = null;
        stopRequested = false;

        if (activeZone.stopBtn) {
            activeZone.stopBtn.disabled = false;
            activeZone.stopBtn.textContent = 'Arrêter et analyser';
            activeZone.stopBtn.hidden = false;
        }
        if (activeZone.resetBtn) {
            activeZone.resetBtn.hidden = false;
            activeZone.resetBtn.disabled = false;
            activeZone.resetBtn.textContent = 'Libérer la session';
        }

        setRunning(true);
        showProgress(activeZone, false);

        if (testMode) startTestTimer();
        else stopTestTimer();

        updateProgress(
            activeZone,
            0,
            testMode
                ? 'Mise en file — mode test (' + sessionMinutes + ' min)…'
                : 'Mise en file d’attente Celery…',
            'collecte',
            true
        );

        const payload = { job: job, test_mode: testMode };
        if (keywordId) payload.keyword_id = keywordId;

        fetch(urlLancer, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload),
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, status: response.status, data: data };
                });
            })
            .then(function (res) {
                if (!res.ok) {
                    const msg = (res.data && res.data.message)
                        ? res.data.message
                        : 'Impossible de lancer la collecte. Vérifiez Redis et le worker Celery.';
                    showFailure(activeZone, msg);
                    return;
                }
                if (!res.data.task_id) throw new Error('Identifiant de tâche manquant.');
                currentTaskId = res.data.task_id;
                updateProgress(activeZone, 2, 'Worker Celery démarré…', 'collecte', true);
                verifierStatut(currentTaskId);
            })
            .catch(function () {
                showFailure(activeZone, 'Impossible de lancer la collecte. Vérifiez Redis et le worker Celery.');
            });
    }

    function libererSession(zone) {
        const target = zone || activeZone || zones.test;
        const taskId = currentTaskId;
        const testMode = !target || target.isTest;

        if (pollingTimer) {
            window.clearTimeout(pollingTimer);
            pollingTimer = null;
        }

        if (!urlReset) {
            dismissProgress(target);
            return;
        }

        if (target && target.resetBtn) {
            target.resetBtn.disabled = true;
            target.resetBtn.textContent = 'Libération…';
        }

        fetch(urlReset, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                test_mode: testMode,
                task_id: taskId || '',
                // Ne jamais purger toute la file Celery : elle peut contenir
                // des tâches Beat ou celles d'un autre utilisateur.
                purge_queue: false,
            }),
        })
            .then(function (response) {
                return response.json().catch(function () { return {}; });
            })
            .then(function (data) {
                if (data && data.cancelling && taskId) {
                    stopRequested = true;
                    if (target && target.statutTexte) {
                        target.statutTexte.textContent =
                            data.message || 'Finalisation des données partielles…';
                    }
                    if (target && target.resetBtn) {
                        target.resetBtn.hidden = true;
                    }
                    isRunning = true;
                    currentTaskId = taskId;
                    activeZone = target;
                    pollingTimer = window.setTimeout(function () {
                        verifierStatut(taskId);
                    }, 700);
                    return;
                }
                dismissProgress(target);
                if (data && data.worker_online === false) {
                    window.alert(
                        (data.worker_message || 'Worker Celery inactif.') +
                        '\n\nLancez : .\\scripts\\run_celery_worker.ps1\npuis relancez le test.'
                    );
                }
            })
            .catch(function () {
                dismissProgress(target);
            });
    }

    function arreterCollecte() {
        const zone = activeZone;
        if (!zone || stopRequested || (currentPhase !== 'collecte' && currentPhase !== 'nlp')) return;

        // Pas de task_id ou PENDING bloqué → libération directe
        if (!currentTaskId) {
            libererSession(zone);
            return;
        }

        stopRequested = true;
        if (zone.stopBtn) {
            zone.stopBtn.disabled = true;
            zone.stopBtn.textContent = 'Arrêt en cours…';
        }
        if (zone.statutTexte) {
            zone.statutTexte.textContent = 'Arrêt demandé…';
        }

        fetch(urlArreter, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify({ task_id: currentTaskId }),
        })
            .then(function (response) {
                if (!response.ok) throw new Error('Arrêt refusé.');
                return response.json();
            })
            .then(function (data) {
                if (data.liberated) {
                    showFailure(
                        zone,
                        data.message || 'Session libérée. Vous pouvez relancer un test.'
                    );
                    return;
                }
                if (zone.statutTexte) {
                    zone.statutTexte.textContent = data.message
                        || 'Arrêt demandé — attente de la prochaine pause du worker…';
                }
                if (zone.stopBtn) {
                    zone.stopBtn.hidden = false;
                    zone.stopBtn.disabled = true;
                    zone.stopBtn.textContent = 'Arrêt en cours…';
                }
                if (zone.resetBtn) {
                    zone.resetBtn.hidden = false;
                    zone.resetBtn.disabled = false;
                }
            })
            .catch(function () {
                stopRequested = false;
                if (zone.stopBtn) {
                    zone.stopBtn.disabled = false;
                    zone.stopBtn.textContent = 'Arrêter et analyser';
                }
            });
    }

    app.querySelectorAll('.collecte-job-btn:not(.collecte-test-btn)').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const job = btn.dataset.job;
            if (!job || job === jobKeyword) return;
            demarrerCollecte(job, null, false);
        });
    });

    app.querySelectorAll('.collecte-test-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const job = btn.dataset.job;
            if (!job) return;
            demarrerCollecte(job, null, true);
        });
    });

    if (keywordBtn) {
        keywordBtn.addEventListener('click', function () {
            const keywordId = keywordSelect && keywordSelect.value;
            if (!keywordId) return;
            demarrerCollecte(jobKeyword, parseInt(keywordId, 10), false);
        });
    }

    if (testKeywordBtn) {
        testKeywordBtn.addEventListener('click', function () {
            const keywordId = testKeywordSelect && testKeywordSelect.value;
            if (!keywordId) return;
            demarrerCollecte(jobKeyword, parseInt(keywordId, 10), true);
        });
    }

    Object.keys(zones).forEach(function (key) {
        const z = zones[key];
        if (z.stopBtn) z.stopBtn.addEventListener('click', arreterCollecte);
        if (z.resetBtn) {
            z.resetBtn.addEventListener('click', function () {
                libererSession(z);
            });
        }
    });

    app.querySelectorAll('.collecte-result-reload').forEach(function (btn) {
        btn.addEventListener('click', function () {
            window.location.href = urlIntelligence;
        });
    });

    const activeTestId = (app.dataset.activeTest || '').trim();
    const activeProdId = (app.dataset.activeProd || '').trim();

    if (activeTestId) {
        resumeTask(activeTestId, true);
    } else if (activeProdId) {
        resumeTask(activeProdId, false);
    }

    /* ── Panneau Celery (dev local) ── */
    const celeryPanel = document.getElementById('collecte-celery-panel');
    if (celeryPanel) {
        const urlCeleryStatus = celeryPanel.dataset.urlStatus;
        const urlCeleryStart = celeryPanel.dataset.urlStart;
        const urlCeleryStop = celeryPanel.dataset.urlStop;
        const feedbackEl = document.getElementById('collecte-celery-feedback');
        const workerPill = document.getElementById('celery-worker-pill');
        const workerMeta = document.getElementById('celery-worker-meta');
        const beatPill = document.getElementById('celery-beat-pill');
        const beatMeta = document.getElementById('celery-beat-meta');
        const refreshBtn = document.getElementById('collecte-celery-refresh');

        function setPill(el, online, labelOnline, labelOffline) {
            if (!el) return;
            el.textContent = online ? labelOnline : labelOffline;
            el.classList.toggle('collecte-celery-pill--online', online);
            el.classList.toggle('collecte-celery-pill--offline', !online);
        }

        function showFeedback(message, isError) {
            if (!feedbackEl) return;
            feedbackEl.textContent = message || '';
            feedbackEl.classList.toggle('is-error', !!isError);
        }

        function applyCeleryStatus(data) {
            if (!data) return;
            setPill(workerPill, data.worker_online, 'Actif', 'Inactif');
            if (workerMeta) workerMeta.textContent = data.worker_message || '';
            setPill(beatPill, data.beat_online, 'Actif', 'Inactif');
            if (beatMeta) {
                beatMeta.textContent = data.beat_online
                    ? 'Planificateur actif (PID ' + (data.beat_pid || '—') + ')'
                    : 'Planifie Google Trends, réseaux, Jumia et Jiji aux horaires configurés.';
            }
        }

        function refreshCeleryStatus() {
            return fetch(urlCeleryStatus, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) throw new Error('Statut Celery indisponible');
                    return res.json();
                })
                .then(applyCeleryStatus)
                .catch(function () {
                    showFeedback('Impossible de lire l’état Celery.', true);
                });
        }

        function celeryAction(action, component) {
            const url = action === 'start' ? urlCeleryStart : urlCeleryStop;
            showFeedback('Commande en cours…', false);
            return fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ component: component }),
            })
                .then(function (res) {
                    return res.json().then(function (data) {
                        return { ok: res.ok, data: data };
                    });
                })
                .then(function (payload) {
                    if (payload.data.status) applyCeleryStatus(payload.data.status);
                    if (!payload.ok) {
                        showFeedback(payload.data.message || 'Échec de la commande Celery.', true);
                        return;
                    }
                    showFeedback(payload.data.message || 'Commande exécutée.', false);
                    setTimeout(refreshCeleryStatus, 1500);
                })
                .catch(function () {
                    showFeedback('Erreur réseau lors de la commande Celery.', true);
                });
        }

        celeryPanel.querySelectorAll('[data-action]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                celeryAction(btn.dataset.action, btn.dataset.component);
            });
        });

        if (refreshBtn) refreshBtn.addEventListener('click', refreshCeleryStatus);
        refreshCeleryStatus();
        setInterval(refreshCeleryStatus, 15000);
    }
})();
