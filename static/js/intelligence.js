/**
 * Page Intelligence — onglets, pagination, panneau détails, navigation
 */
(function () {
    var BATCH_SIZE = 10;

    function openDetailsPanel() {
        var toggle = document.getElementById('intelDetailsToggle');
        var body = document.getElementById('intel-details-body');
        if (!toggle || !body) return;
        toggle.setAttribute('aria-expanded', 'true');
        body.hidden = false;
    }

    /* --- Panneau détails repliable --- */
    var detailsToggle = document.getElementById('intelDetailsToggle');
    var detailsBody = document.getElementById('intel-details-body');

    if (detailsToggle && detailsBody) {
        detailsToggle.addEventListener('click', function () {
            var expanded = detailsToggle.getAttribute('aria-expanded') === 'true';
            detailsToggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
            detailsBody.hidden = expanded;
        });
    }

    /* --- Liens scroll + ouverture panneau (Google Trends uniquement) --- */
    document.querySelectorAll('.js-intel-scroll').forEach(function (link) {
        link.addEventListener('click', function (event) {
            var href = link.getAttribute('href');
            if (!href || href.charAt(0) !== '#') return;

            event.preventDefault();

            if (href === '#decouvertes') {
                openDetailsPanel();
            }

            var target = document.querySelector(href);
            if (target) {
                var delay = href === '#decouvertes' ? 180 : 0;
                setTimeout(function () {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    target.classList.add('intel-discovered--highlight');
                }, delay);
            }
        });
    });

    /* --- Onglets domaine --- */
    var tabs = document.querySelectorAll('.intel-tab');
    var panels = document.querySelectorAll('.intel-tab-panel');

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            var target = tab.getAttribute('data-tab');

            tabs.forEach(function (t) {
                t.classList.remove('is-active');
                t.setAttribute('aria-selected', 'false');
            });
            panels.forEach(function (p) {
                p.classList.remove('is-active');
            });

            tab.classList.add('is-active');
            tab.setAttribute('aria-selected', 'true');

            var panel = document.querySelector('.intel-tab-panel[data-panel="' + target + '"]');
            if (panel) panel.classList.add('is-active');
        });
    });

    /* --- Pagination « Voir plus » --- */
    function initLoadMore(container, itemSelector, button) {
        var batchSize = parseInt(container.getAttribute('data-batch-size'), 10) || BATCH_SIZE;
        var items = container.querySelectorAll(itemSelector);

        if (!items.length || !button) return;

        var visible = Math.min(batchSize, items.length);

        function updateVisibility() {
            items.forEach(function (item, index) {
                item.classList.toggle('is-hidden', index >= visible);
            });

            if (visible >= items.length) {
                button.hidden = true;
            } else {
                button.hidden = false;
                var remaining = items.length - visible;
                button.textContent = 'Voir plus (' + Math.min(batchSize, remaining) + ')';
            }
        }

        button.addEventListener('click', function () {
            visible = Math.min(visible + batchSize, items.length);
            updateVisibility();
        });

        updateVisibility();
    }

    document.querySelectorAll('.js-load-more-table').forEach(function (table) {
        var tbody = table.querySelector('tbody');
        var button = table.parentElement
            ? table.parentElement.nextElementSibling
            : null;

        if (tbody && button && button.classList.contains('js-load-more-btn')) {
            tbody.setAttribute('data-batch-size', table.getAttribute('data-batch-size') || String(BATCH_SIZE));
            initLoadMore(tbody, '.js-load-more-item', button);
        }
    });

    document.querySelectorAll('.js-load-more-grid').forEach(function (grid) {
        var button = grid.nextElementSibling;
        if (button && button.classList.contains('js-load-more-btn')) {
            initLoadMore(grid, '.js-load-more-item', button);
        }
    });

    /* --- Ouverture auto via hash / query --- */
    if (window.location.hash === '#decouvertes') {
        openDetailsPanel();
        var hashSection = document.querySelector(window.location.hash);
        if (hashSection) {
            setTimeout(function () {
                hashSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                hashSection.classList.add('intel-discovered--highlight');
            }, 200);
        }
    }

    if (window.location.hash === '#publications' || window.location.hash === '#social-posts') {
        var pubSection = document.getElementById('publications');
        if (pubSection) {
            setTimeout(function () {
                pubSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                pubSection.classList.add('intel-discovered--highlight');
            }, 150);
        }
    }

    var sectionParam = new URLSearchParams(window.location.search).get('section');
    if (sectionParam === 'social') {
        var socialSection = document.getElementById('publications');
        if (socialSection) {
            setTimeout(function () {
                socialSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                socialSection.classList.add('intel-discovered--highlight');
            }, 150);
        }
    }
})();
