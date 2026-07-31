/**
 * Import Master — poll statut analyse comparative domaines.
 */
(function () {
    const section = document.getElementById('im-domaines');
    if (!section) return;
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
