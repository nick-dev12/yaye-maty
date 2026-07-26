/**

 * Sidebar responsive + réduction desktop — YAYEMATY MARKET

 */

(function () {

    const sidebar = document.getElementById('sidebar');

    const dashboardApp = document.getElementById('dashboardApp');

    const overlay = document.getElementById('sidebarOverlay');

    const menuToggle = document.getElementById('menuToggle');

    const sidebarClose = document.getElementById('sidebarClose');

    const collapseBtn = document.getElementById('sidebarCollapseBtn');

    const searchInput = document.getElementById('sidebarSearch');

    const navLinks = document.querySelectorAll('#sidebarNav .nav-item, #sidebarNav .nav-group-item');

    const STORAGE_KEY = 'yayematy.sidebar.collapsed';



    if (!sidebar || !overlay || !menuToggle) return;



    function openSidebar() {

        sidebar.classList.add('is-open');

        overlay.classList.add('is-visible');

        document.body.classList.add('menu-open');

        menuToggle.setAttribute('aria-expanded', 'true');

        menuToggle.setAttribute('aria-label', 'Fermer le menu');

    }



    function closeSidebar() {

        sidebar.classList.remove('is-open');

        overlay.classList.remove('is-visible');

        document.body.classList.remove('menu-open');

        menuToggle.setAttribute('aria-expanded', 'false');

        menuToggle.setAttribute('aria-label', 'Ouvrir le menu');

    }



    function toggleSidebar() {

        if (sidebar.classList.contains('is-open')) {

            closeSidebar();

        } else {

            openSidebar();

        }

    }



    function setCollapsed(collapsed) {

        if (!dashboardApp) return;

        dashboardApp.classList.toggle('is-sidebar-collapsed', collapsed);

        if (collapseBtn) {

            collapseBtn.setAttribute('aria-pressed', collapsed ? 'true' : 'false');

            collapseBtn.setAttribute('aria-label', collapsed ? 'Développer le menu' : 'Réduire le menu');

        }

        try {

            localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');

        } catch (e) {

            /* ignore */

        }

    }



    function filterNavItems(query) {

        const normalized = query.trim().toLowerCase();

        navLinks.forEach(function (link) {

            const label = (link.getAttribute('data-nav-label') || link.textContent || '').toLowerCase();

            link.classList.toggle('is-hidden', normalized !== '' && !label.includes(normalized));

        });



        document.querySelectorAll('#sidebarNav .sidebar-section-title').forEach(function (title) {

            let section = title.nextElementSibling;

            let visible = false;

            while (section && !section.classList.contains('sidebar-section-title')) {

                if (section.matches('.nav-item, .nav-group-item') && !section.classList.contains('is-hidden')) {

                    visible = true;

                    break;

                }

                section = section.nextElementSibling;

            }

            title.classList.toggle('is-hidden', normalized !== '' && !visible);

        });

    }



    menuToggle.addEventListener('click', toggleSidebar);



    if (sidebarClose) {

        sidebarClose.addEventListener('click', closeSidebar);

    }



    overlay.addEventListener('click', closeSidebar);



    navLinks.forEach(function (link) {

        link.addEventListener('click', function () {

            if (window.innerWidth <= 1024) {

                closeSidebar();

            }

        });

    });



    if (collapseBtn && dashboardApp) {

        collapseBtn.addEventListener('click', function () {

            setCollapsed(!dashboardApp.classList.contains('is-sidebar-collapsed'));

        });



        if (window.innerWidth > 1024) {

            try {

                setCollapsed(localStorage.getItem(STORAGE_KEY) === '1');

            } catch (e) {

                setCollapsed(false);

            }

        }

    }



    if (searchInput) {

        searchInput.addEventListener('input', function () {

            filterNavItems(searchInput.value);

        });

    }



    document.addEventListener('keydown', function (e) {

        if (e.key === 'Escape' && sidebar.classList.contains('is-open')) {

            closeSidebar();

        }

    });



    window.addEventListener('resize', function () {

        if (window.innerWidth > 1024) {

            closeSidebar();

        } else if (dashboardApp) {

            dashboardApp.classList.remove('is-sidebar-collapsed');

        }

    });

})();


