// Mode state
let mode = 'login';   // 'login' or 'signup'

// Elements
const loginFields = document.getElementById('loginFields');
const signupFields = document.getElementById('signupFields');
const submitBtn = document.getElementById('submitBtn');
const switchHint = document.getElementById('switchHint');
const switchLink = document.getElementById('switchLink');
const errorMsg = document.getElementById('errorMsg');

const loginUsername = document.getElementById('loginUsername');
const loginPassword = document.getElementById('loginPassword');
const signupUsername = document.getElementById('signupUsername');
const signupPassword = document.getElementById('signupPassword');
const signupConfirm = document.getElementById('signupConfirm');

function showError(message) {
    errorMsg.textContent = message;
    errorMsg.classList.remove('shake');

    if (errorMsg.classList.contains('visible')) {
        // Already visible – just shake
        void errorMsg.offsetWidth; // force reflow to restart animation
        errorMsg.classList.add('shake');
        return;
    }

    // First time showing error: fade in then shake
    errorMsg.classList.add('visible');   // triggers opacity transition
    const onFadeEnd = () => {
        errorMsg.removeEventListener('transitionend', onFadeEnd);
        errorMsg.classList.add('shake');
    };
    errorMsg.addEventListener('transitionend', onFadeEnd);
    // Fallback
    setTimeout(() => {
        if (!errorMsg.classList.contains('shake')) {
            errorMsg.classList.add('shake');
        }
    }, 300);
}

function clearError() {
    if (!errorMsg.classList.contains('visible')) return;
    errorMsg.classList.remove('visible', 'shake');
}

// Switch between modes
function setMode(newMode) {
    if (mode === newMode) return;
    mode = newMode;
    clearError();

    if (mode === 'login') {
        loginFields.style.display = '';
        signupFields.style.display = 'none';
        submitBtn.textContent = 'Login';
        switchHint.textContent = "Don't have an account?";
        switchLink.textContent = 'Sign up';
        loginUsername.focus();
    } else {
        loginFields.style.display = 'none';
        signupFields.style.display = '';
        submitBtn.textContent = 'Sign Up';
        switchHint.textContent = 'Already have an account?';
        switchLink.textContent = 'Log in';
        // Copy values if any
        if (loginUsername.value) signupUsername.value = loginUsername.value;
        if (loginPassword.value) signupPassword.value = loginPassword.value;
        signupUsername.focus();
    }
}

switchLink.addEventListener('click', () => {
    setMode(mode === 'login' ? 'signup' : 'login');
});

// Form submission
submitBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    clearError();

    if (mode === 'login') {
        const username = loginUsername.value.trim();
        const password = loginPassword.value;
        if (!username || !password) {
            showError('Username and password required');
            return;
        }
        submitBtn.disabled = true;
        submitBtn.textContent = 'Logging in...';
        try {
            const resp = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await resp.json();
            if (resp.ok) {
                // Success – navigate away immediately; no need to reset button
                window.location.href = '/chat';
                return;
            }
            // Login failed
            showError(data.error || 'Login failed');
        } catch {
            showError('Network error');
        }
        // Only on failure do we re-enable the button
        submitBtn.disabled = false;
        submitBtn.textContent = 'Login';
    } else {
        const username = signupUsername.value.trim();
        const password = signupPassword.value;
        const confirm = signupConfirm.value;
        if (!username || !password || !confirm) {
            showError('All fields are required');
            return;
        }
        if (password.length < 6) {
            showError('Password must be at least 6 characters');
            return;
        }
        if (password !== confirm) {
            showError('Passwords do not match');
            return;
        }
        submitBtn.disabled = true;
        submitBtn.textContent = 'Signing up...';
        try {
            const resp = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await resp.json();
            if (resp.ok) {
                // Auto-login and redirect
                const loginResp = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                if (loginResp.ok) {
                    window.location.href = '/chat';
                    return;
                }
                // Fallback: login failed but signup succeeded
                window.location.href = '/?username=' + encodeURIComponent(username);
                return;
            }
            showError(data.error || 'Signup failed');
        } catch {
            showError('Network error');
        }
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign Up';
    }
});

// Allow Enter key to submit
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        submitBtn.click();
    }
});

// Focus first input on load
loginUsername.focus();