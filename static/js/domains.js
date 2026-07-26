/**
 * Onglets et panneaux — page Intelligence / Domaines
 */
(function () {
    var tabs = document.querySelectorAll('.js-domains-tab');
    var panels = document.querySelectorAll('.js-domains-panel');
    if (!tabs.length || !panels.length) return;

    var validPanels = ['gestion', 'decouverte'];

    function showPanel(panelId) {
        var target = validPanels.indexOf(panelId) !== -1 ? panelId : 'gestion';

        tabs.forEach(function (tab) {
            var isActive = tab.getAttribute('data-panel') === target;
            tab.classList.toggle('is-active', isActive);
            tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        panels.forEach(function (panel) {
            var isActive = panel.getAttribute('data-panel') === target;
            panel.classList.toggle('is-visible', isActive);
            if (isActive) {
                panel.removeAttribute('hidden');
            } else {
                panel.setAttribute('hidden', '');
            }
        });

        history.replaceState(null, '', '#' + target);
    }

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            showPanel(tab.getAttribute('data-panel') || 'gestion');
        });
    });

    window.addEventListener('hashchange', function () {
        var hash = window.location.hash.replace('#', '');
        showPanel(hash || 'gestion');
    });

    var initial = window.location.hash.replace('#', '') || 'gestion';
    showPanel(initial);
})();
