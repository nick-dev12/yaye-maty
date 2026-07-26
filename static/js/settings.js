/**

 * Navigation, limite de sélection et modals — Page Paramètres

 */

(function () {

    var validSections = ['wolof', 'recherche', 'sources', 'compte'];

    var hash = window.location.hash.replace('#', '');

    var sectionParam = new URLSearchParams(window.location.search).get('section');

    var active = sectionParam || hash;



    if (active && validSections.indexOf(active) !== -1) {

        document.querySelectorAll('.settings-nav-item').forEach(function (item) {

            item.classList.toggle('is-active', item.getAttribute('data-section') === active);

        });

        document.querySelectorAll('.settings-panel').forEach(function (panel) {

            panel.classList.toggle('is-visible', panel.getAttribute('data-panel') === active);

        });

    }



    function setupModal(openSelector, modalSelector, closeSelector, formSelector) {

        var modal = document.querySelector(modalSelector);

        var openBtns = document.querySelectorAll(openSelector);
        var closeBtns = document.querySelectorAll(closeSelector);
        var form = formSelector ? document.querySelector(formSelector) : null;

        function openModal() {
            if (!modal) return;
            modal.classList.remove('is-hidden');
            document.body.classList.add('settings-modal-open');
            var firstInput = form && form.querySelector('input:not([type="hidden"]), textarea, select');
            if (firstInput) {
                window.setTimeout(function () {
                    firstInput.focus();
                }, 50);
            }
        }

        function closeModal() {
            if (!modal) return;
            modal.classList.add('is-hidden');
            document.body.classList.remove('settings-modal-open');
        }

        openBtns.forEach(function (btn) {
            btn.addEventListener('click', openModal);
        });



        closeBtns.forEach(function (btn) {

            btn.addEventListener('click', closeModal);

        });



        document.addEventListener('keydown', function (event) {

            if (event.key === 'Escape' && modal && !modal.classList.contains('is-hidden')) {

                closeModal();

            }

        });

    }



    setupModal(

        '.js-open-add-domain',

        '.js-add-domain-modal',

        '.js-close-add-domain',

        '.js-add-domain-form'

    );



    setupModal(

        '.js-open-wolof-modal',

        '.js-wolof-modal',

        '.js-close-wolof-modal',

        '.js-wolof-form'

    );



    setupModal(
        '.js-open-search-modal',
        '.js-search-modal',
        '.js-close-search-modal',
        '.js-search-form'
    );

    setupModal(
        '.js-open-marketplace-modal',
        '.js-marketplace-modal',
        '.js-close-marketplace-modal',
        '.js-marketplace-form'
    );



    var limitForm = document.querySelector('.js-domain-limit-form');
    if (limitForm) {
        var max = parseInt(limitForm.getAttribute('data-max'), 10) || 2;
        var checkboxes = limitForm.querySelectorAll('.js-domain-checkboxes input[type="checkbox"]');

        checkboxes.forEach(function (checkbox) {
            checkbox.addEventListener('change', function () {
                var checked = limitForm.querySelectorAll('.js-domain-checkboxes input[type="checkbox"]:checked');
                if (checked.length > max) {
                    checkbox.checked = false;
                    alert('Maximum ' + max + ' domaine(s) sélectionnable(s) (limite Google Trends).');
                }
            });
        });
    }
})();
