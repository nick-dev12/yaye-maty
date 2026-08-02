/**
 * Import Master — modale domaines + poll statut analyse.
 */
(function () {
    const section = document.getElementById('im-domaines');
    if (!section) return;

    /* ---------- Modale sélection domaines ---------- */
    const modal = document.getElementById('im-domain-modal');
    const openBtn = document.getElementById('im-open-domain-modal');
    const closeBtn = document.getElementById('im-domain-modal-close');
    const cancelBtn = document.getElementById('im-domain-modal-cancel');
    const backdrop = document.getElementById('im-domain-modal-backdrop');
    const searchInput = document.getElementById('im-domain-search');
    const selectAllBtn = document.getElementById('im-domain-select-all');
    const list = document.getElementById('im-domain-list');
    const countEl = document.getElementById('im-domain-count');
    const form = document.getElementById('im-domain-form');
    const submitBtn = document.getElementById('im-domain-submit');

    function domainChecks() {
        return list ? Array.from(list.querySelectorAll('.im-domain-check')) : [];
    }

    function visibleChecks() {
        return domainChecks().filter((el) => !el.hidden);
    }

    function updateCount() {
        if (!countEl) return;
        const checked = domainChecks().filter(
            (el) => el.querySelector('input') && el.querySelector('input').checked,
        ).length;
        const total = domainChecks().length;
        countEl.textContent = total
            ? `${checked} / ${total} domaine${total > 1 ? 's' : ''} sélectionné${checked > 1 ? 's' : ''}`
            : '';
        if (submitBtn) submitBtn.disabled = checked === 0;
    }

    function openModal() {
        if (!modal || !openBtn || openBtn.disabled) return;
        modal.hidden = false;
        modal.classList.remove('is-hidden');
        document.body.classList.add('im-modal-open');
        updateCount();
        if (searchInput) {
            searchInput.value = '';
            filterDomains('');
            setTimeout(() => searchInput.focus(), 40);
        }
    }

    function closeModal() {
        if (!modal) return;
        modal.hidden = true;
        modal.classList.add('is-hidden');
        document.body.classList.remove('im-modal-open');
    }

    function filterDomains(query) {
        const q = (query || '').trim().toLowerCase();
        domainChecks().forEach((el) => {
            const label = el.getAttribute('data-domain-label') || '';
            el.hidden = Boolean(q) && !label.includes(q);
        });
        if (selectAllBtn) {
            const visible = visibleChecks();
            const allOn = visible.length > 0 && visible.every(
                (el) => el.querySelector('input') && el.querySelector('input').checked,
            );
            selectAllBtn.textContent = allOn ? 'Tout désélectionner' : 'Tout sélectionner';
        }
    }

    if (openBtn) openBtn.addEventListener('click', openModal);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    if (backdrop) backdrop.addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal && !modal.hidden) closeModal();
    });

    if (searchInput) {
        searchInput.addEventListener('input', () => filterDomains(searchInput.value));
    }

    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', () => {
            const visible = visibleChecks();
            const allOn = visible.length > 0 && visible.every(
                (el) => el.querySelector('input') && el.querySelector('input').checked,
            );
            visible.forEach((el) => {
                const input = el.querySelector('input');
                if (input) input.checked = !allOn;
            });
            selectAllBtn.textContent = allOn ? 'Tout sélectionner' : 'Tout désélectionner';
            updateCount();
        });
    }

    if (list) {
        list.addEventListener('change', updateCount);
    }

    if (form) {
        form.addEventListener('submit', (e) => {
            const checked = domainChecks().some(
                (el) => el.querySelector('input') && el.querySelector('input').checked,
            );
            if (!checked) {
                e.preventDefault();
                updateCount();
            }
        });
    }

    updateCount();

    /* ---------- Poll statut ---------- */
    const running = section.dataset.running === '1';
    const url = section.dataset.statusUrl;
    if (!running || !url) return;

    const bar = section.querySelector('.im-domain-progress-bar');
    const msg = section.querySelector('.im-domain-progress-msg');
    let ticks = 0;

    function tick() {
        ticks += 1;
        fetch(url, { credentials: 'same-origin' })
            .then((r) => r.json())
            .then((data) => {
                if (!data || !data.ok) return;
                if (bar && data.progress_percent != null) {
                    bar.style.width = `${Math.max(5, data.progress_percent)}%`;
                }
                if (msg && data.progress_message) {
                    msg.textContent = data.progress_message;
                }
                if (data.done || data.failed) {
                    window.location.reload();
                    return;
                }
                if (ticks < 120) {
                    setTimeout(tick, 2500);
                }
            })
            .catch(() => {
                if (ticks < 120) setTimeout(tick, 4000);
            });
    }

    setTimeout(tick, 1500);
})();
