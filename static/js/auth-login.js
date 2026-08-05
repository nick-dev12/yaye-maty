/**
 * Connexion — bascule dynamique vers réinitialisation mot de passe.
 */
(function () {
    'use strict';

    const card = document.querySelector('.auth-card--switchable');
    if (!card) return;

    const panels = {
        login: document.getElementById('auth-panel-login'),
        reset: document.getElementById('auth-panel-reset'),
    };

    function showPanel(name) {
        Object.entries(panels).forEach(([key, panel]) => {
            if (!panel) return;
            const active = key === name;
            panel.hidden = !active;
            panel.classList.toggle('is-active', active);
        });
        if (name === 'reset') {
            const emailInput = document.getElementById('id_reset_email');
            if (emailInput) setTimeout(() => emailInput.focus(), 120);
        } else {
            const userInput = document.getElementById('id_username');
            if (userInput) setTimeout(() => userInput.focus(), 120);
        }
    }

    document.querySelectorAll('[data-auth-show]').forEach((btn) => {
        btn.addEventListener('click', () => {
            showPanel(btn.getAttribute('data-auth-show') || 'login');
        });
    });

    const resetForm = document.getElementById('auth-reset-form');
    const resetSubmit = document.getElementById('auth-reset-submit');
    if (resetForm && resetSubmit) {
        resetForm.addEventListener('submit', () => {
            resetSubmit.disabled = true;
            resetSubmit.querySelector('span').textContent = 'Envoi en cours…';
        });
    }

    if (window.location.hash === '#reset') {
        showPanel('reset');
    }
})();
