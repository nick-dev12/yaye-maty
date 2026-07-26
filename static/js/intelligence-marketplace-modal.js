/**
 * Modale liens annonces Jiji / produits Jumia
 */
(function () {
    'use strict';

    var modal = document.getElementById('marketplace-links-modal');
    if (!modal) return;

    var titleEl = document.getElementById('mp-modal-title');
    var listEl = document.getElementById('mp-modal-list');
    var emptyEl = document.getElementById('mp-modal-empty');
    var lastFocus = null;

    function formatPrice(value) {
        if (value === null || value === undefined || value === '') return '';
        var n = Number(value);
        if (Number.isNaN(n)) return '';
        return n.toLocaleString('fr-FR') + ' FCFA';
    }

    function buildMeta(item, source) {
        var parts = [];
        if (source === 'jiji') {
            if (item.views_count) parts.push(item.views_count + ' vues');
            if (item.condition) parts.push(item.condition);
            if (item.location) parts.push(item.location);
        } else {
            if (item.rating_count) parts.push(item.rating_count + ' avis');
            if (item.rating_value) parts.push(item.rating_value + '★');
            if (item.stock_status) parts.push(item.stock_status);
        }
        if (item.price_xof) parts.push(formatPrice(item.price_xof));
        return parts.join(' · ');
    }

    function renderList(items, source) {
        listEl.innerHTML = '';
        if (!items || !items.length) {
            emptyEl.hidden = false;
            return;
        }
        emptyEl.hidden = true;
        items.forEach(function (item) {
            var li = document.createElement('li');
            li.className = 'mp-modal-item';
            var link = document.createElement('a');
            link.className = 'mp-modal-link';
            link.href = item.url || '#';
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = item.title || 'Sans titre';
            if (!item.url) {
                link.classList.add('is-disabled');
                link.removeAttribute('href');
            }
            var meta = document.createElement('span');
            meta.className = 'mp-modal-meta';
            meta.textContent = buildMeta(item, source);
            li.appendChild(link);
            if (meta.textContent) li.appendChild(meta);
            listEl.appendChild(li);
        });
    }

    function openModal(title, items, source) {
        lastFocus = document.activeElement;
        titleEl.textContent = title || 'Annonces';
        renderList(items, source || 'jiji');
        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('mp-modal-open');
        var closeBtn = modal.querySelector('.mp-modal-close');
        if (closeBtn) closeBtn.focus();
    }

    function closeModal() {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('mp-modal-open');
        if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
    }

    document.querySelectorAll('.js-marketplace-modal-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var raw = btn.getAttribute('data-items') || '[]';
            var items = [];
            try {
                items = JSON.parse(raw);
            } catch (e) {
                items = [];
            }
            openModal(
                btn.getAttribute('data-modal-title') || 'Annonces',
                items,
                btn.getAttribute('data-source') || 'jiji'
            );
        });
    });

    modal.querySelectorAll('.js-mp-modal-close').forEach(function (el) {
        el.addEventListener('click', closeModal);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.hidden) closeModal();
    });
})();
