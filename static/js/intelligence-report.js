/**
 * Intelligence report — onglets Top 10 & navigation sticky
 */
(function () {
    'use strict';

    function activateTab(tabId) {
        if (!tabId) return;

        document.querySelectorAll('[data-ir10-tab]').forEach(function (el) {
            if (el.getAttribute('role') === 'tab') {
                var isActive = el.getAttribute('data-ir10-tab') === tabId;
                el.classList.toggle('ir10-tab--active', isActive);
                el.setAttribute('aria-selected', isActive ? 'true' : 'false');
            }
        });

        document.querySelectorAll('[data-ir10-panel]').forEach(function (panel) {
            var show = panel.getAttribute('data-ir10-panel') === tabId;
            panel.hidden = !show;
            panel.classList.toggle('ir10-panel--active', show);
        });
    }

    function initTabs() {
        var hub = document.getElementById('top10-hub');
        if (!hub) return;

        hub.querySelectorAll('[role="tab"]').forEach(function (tab) {
            tab.addEventListener('click', function () {
                activateTab(tab.getAttribute('data-ir10-tab'));
            });
        });

        document.querySelectorAll('[data-ir10-tab]').forEach(function (link) {
            if (link.getAttribute('role') === 'tab') return;
            link.addEventListener('click', function (e) {
                var tabId = link.getAttribute('data-ir10-tab');
                if (!tabId) return;
                activateTab(tabId);
            });
        });
    }

    function initNavHighlight() {
        var sections = [
            { id: 'intel-resume', link: 'intel-resume' },
            { id: 'top10-hub', link: 'top10-hub' },
            { id: 'intel-expert', link: 'intel-expert' },
        ];

        if (!('IntersectionObserver' in window)) return;

        var navLinks = document.querySelectorAll('.ir10-nav-link');
        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (!entry.isIntersecting) return;
                    var id = entry.target.id;
                    navLinks.forEach(function (link) {
                        var href = link.getAttribute('href') || '';
                        link.classList.toggle('ir10-nav-link--active', href === '#' + id);
                    });
                });
            },
            { rootMargin: '-30% 0px -55% 0px', threshold: 0 }
        );

        sections.forEach(function (s) {
            var el = document.getElementById(s.id);
            if (el) observer.observe(el);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initTabs();
            initNavHighlight();
        });
    } else {
        initTabs();
        initNavHighlight();
    }
})();
