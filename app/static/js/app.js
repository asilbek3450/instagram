// ═══════════════════════════════════════════════════════════════
//  InstaTrack Pro — Global App Logic
// ═══════════════════════════════════════════════════════════════

let activeAccount = { id: null, username: null, is_simulated: true };

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    highlightSidebar();
    initThemeIcon();
    displayUserInfo();
    fetchAccounts();

    // Demo mode form submit
    const linkForm = document.getElementById('link-account-form');
    if (linkForm) linkForm.addEventListener('submit', connectDemoAccount);

    // Show OAuth success toast if redirected back with ?ig_connected=1
    const params = new URLSearchParams(window.location.search);
    if (params.get('ig_connected') === '1') {
        const synced = params.get('sync') === 'synced';
        showAlert('success',
            `<i class="bi bi-instagram me-2"></i><strong>Instagram connected!</strong> ` +
            (synced ? 'Your real data has been imported.' : 'Data sync is in progress — refresh in a moment.'),
            false
        );
        // Clean URL
        window.history.replaceState({}, '', window.location.pathname);
    }
});

// ── Sidebar highlight ─────────────────────────────────────────────────────────
function highlightSidebar() {
    const path = window.location.pathname;
    const navMap = {
        '/dashboard':  'nav-dashboard',
        '/followers':  'nav-followers',
        '/posts':      'nav-posts',
        '/stories':    'nav-stories',
        '/comments':   'nav-comments',
        '/ai-features':'nav-ai',
        '/reports':    'nav-reports',
        '/profile':    'nav-profile',
        '/admin':      'nav-admin'
    };
    const activeId = navMap[path];
    if (activeId) {
        const link = document.getElementById(activeId);
        if (link) {
            link.classList.add('active');
            const pageTitleEl = document.getElementById('page-title');
            if (pageTitleEl) pageTitleEl.textContent = link.innerText.trim();
        }
    }
}

// ── User info display ─────────────────────────────────────────────────────────
function displayUserInfo() {
    const user = getCurrentUser();
    if (user) {
        const emailEl = document.getElementById('user-email-display');
        const roleEl  = document.getElementById('user-role-display');
        const adminNav = document.getElementById('admin-nav-item');

        if (emailEl) emailEl.textContent = user.email;
        if (roleEl)  roleEl.textContent  = user.role.charAt(0).toUpperCase() + user.role.slice(1);
        if (user.role === 'admin' && adminNav) adminNav.classList.remove('d-none');
    }
}

// ── Fetch accounts from API ───────────────────────────────────────────────────
async function fetchAccounts() {
    const token = getAccessToken();
    if (!token) return;

    try {
        const res = await fetch('/api/analytics/accounts', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) return;
        const data = await res.json();

        // Pick up account ID set by OAuth callback cookie
        const cookie = document.cookie.split('; ').find(r => r.startsWith('last_connected_account_id='));
        if (cookie) {
            const id = cookie.split('=')[1];
            if (id) localStorage.setItem('active_account_id', id);
            document.cookie = 'last_connected_account_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        }

        populateAccountSelector(data.accounts);
    } catch (e) {
        console.error('fetchAccounts error', e);
    }
}

// ── Populate account dropdown ─────────────────────────────────────────────────
function populateAccountSelector(accounts) {
    const listEl  = document.getElementById('account-selector-list');
    const labelEl = document.getElementById('active-account-name');
    if (!listEl) return;

    listEl.innerHTML = '';

    if (!accounts || accounts.length === 0) {
        listEl.innerHTML = `
            <li><a class="dropdown-item text-muted disabled" href="#">No accounts linked</a></li>
            <li><hr class="dropdown-divider"></li>
            <li><a class="dropdown-item text-primary fw-bold" href="#"
                data-bs-toggle="modal" data-bs-target="#linkAccountModal">
                <i class="bi bi-plus-circle me-2"></i>Link Account</a></li>`;
        if (labelEl) labelEl.textContent = 'Link Instagram';

        const analysisPaths = ['/dashboard','/followers','/posts','/stories','/comments','/ai-features','/reports'];
        if (analysisPaths.includes(window.location.pathname)) {
            showAlert('warning', 'Please link an Instagram account to see analytics data.', true);
        }

        // Hide sync button
        toggleSyncButton(false);
        return;
    }

    let savedId  = localStorage.getItem('active_account_id');
    let activeAcc = accounts.find(a => a.id == savedId) || accounts[0];

    activeAccount.id          = activeAcc.id;
    activeAccount.username    = activeAcc.username;
    activeAccount.is_simulated = activeAcc.is_simulated;

    localStorage.setItem('active_account_id',       activeAcc.id);
    localStorage.setItem('active_account_username', activeAcc.username);

    if (labelEl) labelEl.textContent = `@${activeAcc.username}`;

    accounts.forEach(acc => {
        const isActive = acc.id == activeAccount.id;
        const badge = acc.is_simulated
            ? `<span class="badge bg-secondary" style="font-size:9px">SIM</span>`
            : `<span class="badge bg-success" style="font-size:9px">LIVE</span>`;
        const li = document.createElement('li');
        li.innerHTML = `
            <a class="dropdown-item d-flex justify-content-between align-items-center ${isActive ? 'active' : ''}"
               href="#" onclick="selectActiveAccount(${acc.id}, '${acc.username}', ${acc.is_simulated})">
                <span>@${acc.username}</span>
                ${badge}
            </a>`;
        listEl.appendChild(li);
    });

    const divider = document.createElement('li');
    divider.innerHTML = '<hr class="dropdown-divider">';
    listEl.appendChild(divider);

    const linkBtn = document.createElement('li');
    linkBtn.innerHTML = `<a class="dropdown-item text-primary fw-bold" href="#"
        data-bs-toggle="modal" data-bs-target="#linkAccountModal">
        <i class="bi bi-plus-circle me-2"></i>Link Account</a>`;
    listEl.appendChild(linkBtn);

    // Show/hide sync button based on whether the active account is real
    toggleSyncButton(!activeAcc.is_simulated);

    // Dispatch change event
    document.dispatchEvent(new CustomEvent('activeAccountChanged', { detail: activeAccount }));
}

// ── Select active account ─────────────────────────────────────────────────────
function selectActiveAccount(id, username, isSimulated) {
    activeAccount.id          = id;
    activeAccount.username    = username;
    activeAccount.is_simulated = isSimulated;

    localStorage.setItem('active_account_id',       id);
    localStorage.setItem('active_account_username', username);

    const labelEl = document.getElementById('active-account-name');
    if (labelEl) labelEl.textContent = `@${username}`;

    toggleSyncButton(!isSimulated);

    fetchAccounts();
    document.dispatchEvent(new CustomEvent('activeAccountChanged', { detail: activeAccount }));
}

// ── Sync button visibility ────────────────────────────────────────────────────
function toggleSyncButton(show) {
    const btn = document.getElementById('sync-now-btn');
    if (btn) btn.classList.toggle('d-none', !show);
}

// ── Demo account connect form ─────────────────────────────────────────────────
async function connectDemoAccount(e) {
    e.preventDefault();
    const username = document.getElementById('insta-username').value.trim();
    const token    = getAccessToken();
    if (!username || !token) return;

    const btn = document.getElementById('connect-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Connecting...'; }

    try {
        const res = await fetch('/api/analytics/accounts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ username, is_simulated: true })
        });
        const data = await res.json();

        const modalEl = document.getElementById('linkAccountModal');
        const modal   = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();

        if (res.ok) {
            showAlert('success', `<i class="bi bi-cpu me-1"></i> Demo account <strong>@${username}</strong> connected! Loading metrics...`);
            document.getElementById('insta-username').value = '';
            localStorage.setItem('active_account_id', data.account.id);
            fetchAccounts();
        } else {
            showAlert('danger', data.error || 'Failed to connect demo account.');
        }
    } catch {
        showAlert('danger', 'Server connection error.');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="bi bi-cpu me-1"></i>Connect Demo Account'; }
    }
}

// ── Real Instagram OAuth connect ──────────────────────────────────────────────
function connectRealInstagram() {
    const token = getAccessToken();
    if (!token) {
        showAlert('warning', 'Please log in again before connecting Instagram.');
        return;
    }

    const btn = document.getElementById('oauth-connect-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Awaiting Auth...';
    }

    const width = 500;
    const height = 700;
    const left = (window.screen.width / 2) - (width / 2);
    const top = (window.screen.height / 2) - (height / 2);

    // A popup window can't carry the Authorization header, so pass the JWT via
    // the query string (flask-jwt-extended reads it as the `jwt` param).
    const url = `/api/auth/instagram/login?jwt=${encodeURIComponent(token)}`;
    window.open(url, 'InstagramAuth', `width=${width},height=${height},top=${top},left=${left},toolbar=no,menubar=no,scrollbars=yes`);
}

// ── Listen for OAuth Popup Messages ───────────────────────────────────────────
window.addEventListener('message', (event) => {
    // Ensure the message is from our own origin
    if (event.origin !== window.location.origin) return;
    
    if (event.data && event.data.type === 'INSTAGRAM_AUTH_SUCCESS') {
        const synced = event.data.sync === 'synced';
        const accountId = event.data.accountId;
        
        // Hide the modal
        const modalEl = document.getElementById('linkAccountModal');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }
        
        // Reset button
        const btn = document.getElementById('oauth-connect-btn');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-instagram me-2"></i>Continue with Instagram';
        }
        
        // Set active account locally
        if (accountId) localStorage.setItem('active_account_id', accountId);
        
        fetchAccounts();
        
        showAlert('success',
            `<i class="bi bi-instagram me-2"></i><strong>Instagram connected!</strong> ` +
            (synced ? 'Your real data has been imported.' : 'Data sync is in progress — refresh in a moment.'),
            false
        );
    } else if (event.data && event.data.type === 'INSTAGRAM_AUTH_ERROR') {
        // Reset button
        const btn = document.getElementById('oauth-connect-btn');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-instagram me-2"></i>Continue with Instagram';
        }
        
        showAlert('danger', `Authentication failed: ${event.data.error || 'Unknown error'}`);
    }
});

// ── Sync Now ──────────────────────────────────────────────────────────────────
async function syncNow() {
    const token     = getAccessToken();
    const accountId = activeAccount.id;
    if (!token || !accountId) return;

    const btn  = document.getElementById('sync-now-btn');
    const icon = document.getElementById('sync-icon');

    if (btn)  btn.disabled = true;
    if (icon) icon.className = 'bi bi-arrow-repeat spin';

    showAlert('info', '<i class="bi bi-arrow-repeat me-1"></i>Syncing data from Instagram API…');

    try {
        const res  = await fetch(`/api/instagram/sync/${accountId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();

        if (res.ok) {
            const ts = data.last_synced_at
                ? new Date(data.last_synced_at).toLocaleTimeString()
                : 'just now';
            showAlert('success', `<i class="bi bi-check-circle me-1"></i>Sync complete at <strong>${ts}</strong>. Refreshing data...`);

            // Trigger page data reload
            setTimeout(() => {
                document.dispatchEvent(new CustomEvent('activeAccountChanged', { detail: activeAccount }));
            }, 600);
        } else {
            showAlert('danger', `<i class="bi bi-exclamation-triangle me-1"></i>${data.error || 'Sync failed.'}`);
        }
    } catch (e) {
        showAlert('danger', 'Network error during sync.');
    } finally {
        if (btn)  btn.disabled = false;
        if (icon) icon.className = 'bi bi-arrow-repeat';
    }
}

// ── Alert helper ──────────────────────────────────────────────────────────────
function showAlert(type, message, persistent = false) {
    const container = document.getElementById('alert-container');
    if (!container) return;

    const id = 'alert_' + Date.now();
    const iconMap = {
        danger:  'bi-exclamation-triangle-fill',
        warning: 'bi-exclamation-circle',
        success: 'bi-check-circle-fill',
        info:    'bi-info-circle-fill'
    };
    const iconClass = iconMap[type] || 'bi-info-circle-fill';

    container.innerHTML = `
        <div class="alert alert-${type} alert-dismissible fade show shadow border-card" id="${id}" role="alert">
            <div class="d-flex align-items-center gap-2">
                <i class="bi ${iconClass}"></i>
                <div>${message}</div>
            </div>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>`;

    if (!persistent) {
        setTimeout(() => {
            const el = document.getElementById(id);
            if (el) {
                const a = bootstrap.Alert.getInstance(el) || new bootstrap.Alert(el);
                a.close();
            }
        }, 6000);
    }
}

// ── Sidebar toggle ────────────────────────────────────────────────────────────
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('active');
}

// ── Theme management ──────────────────────────────────────────────────────────
function initThemeIcon() {
    applyTheme(localStorage.getItem('color-scheme') || 'dark');
}

function applyTheme(scheme) {
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.content = scheme;
    document.documentElement.style.colorScheme = scheme;
    // Bootstrap 5.3 components (nav links, dropdowns, modals, form controls)
    // read the theme from data-bs-theme — without it they stay light and
    // become unreadable on dark backgrounds.
    document.documentElement.setAttribute('data-bs-theme', scheme);

    const icon = document.getElementById('theme-icon');
    if (icon) icon.className = scheme === 'dark' ? 'bi bi-moon-stars' : 'bi bi-sun';

    localStorage.setItem('color-scheme', scheme);
}

function toggleTheme() {
    const next = (localStorage.getItem('color-scheme') || 'dark') === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    showAlert(next === 'dark' ? 'dark' : 'info',
        next === 'dark' ? 'Dark theme activated.' : 'Light theme activated.', false);
    document.dispatchEvent(new CustomEvent('themeChanged', { detail: next }));
}
