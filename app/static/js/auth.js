// Authentication Utility functions

// Get current user details from localStorage
function getCurrentUser() {
    const userStr = localStorage.getItem('user');
    if (!userStr) return null;
    try {
        return JSON.parse(userStr);
    } catch (e) {
        return null;
    }
}

// Get the stored JWT token
function getAccessToken() {
    return localStorage.getItem('access_token');
}

// Check if user is logged in. Redirect to login if not.
function checkAuth() {
    const token = getAccessToken();
    const currentPath = window.location.pathname;
    
    // Whitelisted non-auth paths
    const publicPaths = ['/', '/landing', '/login', '/register'];
    
    if (!token && !publicPaths.includes(currentPath)) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

// Redirect authenticated users away from login/register
function redirectIfAuthenticated() {
    const token = getAccessToken();
    const currentPath = window.location.pathname;
    const authPaths = ['/login', '/register'];
    
    if (token && authPaths.includes(currentPath)) {
        window.location.href = '/dashboard';
    }
}

// Log out user
async function logout() {
    const token = getAccessToken();
    if (token) {
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
        } catch (e) {
            console.error("Failed to call logout API", e);
        }
    }
    
    // Clear local storage
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    localStorage.removeItem('active_account_id');
    localStorage.removeItem('active_account_username');
    
    window.location.href = '/login';
}

// Initialize Auth Checks immediately
checkAuth();
redirectIfAuthenticated();
