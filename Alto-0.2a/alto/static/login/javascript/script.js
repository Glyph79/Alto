const loginTab = document.getElementById('loginTab');
const signupTab = document.getElementById('signupTab');
const loginWrapper = document.getElementById('loginWrapper');
const signupWrapper = document.getElementById('signupWrapper');
const loginForm = document.getElementById('loginForm');
const signupForm = document.getElementById('signupForm');
const formsWrapper = document.querySelector('.auth-forms-wrapper');
const loginUsername = document.getElementById('loginUsername');
const loginPassword = document.getElementById('loginPassword');
const signupUsername = document.getElementById('signupUsername');
const signupPassword = document.getElementById('signupPassword');
const signupConfirmPassword = document.getElementById('signupConfirmPassword');
const loginBtn = document.getElementById('loginBtn');
const signupBtn = document.getElementById('signupBtn');
const loginError = document.getElementById('loginError');
const signupError = document.getElementById('signupError');

let switchTimeout = null;
let loginHeight = 0;
let signupHeight = 0;
let animationInProgress = false;

// Measure heights of the wrappers (which contain the forms)
function measureHeights() {
    const originalDisplayLogin = loginWrapper.style.display;
    const originalDisplaySignup = signupWrapper.style.display;
    const originalLoginErrorVisible = loginError.classList.contains('visible');
    const originalSignupErrorVisible = signupError.classList.contains('visible');

    loginWrapper.style.display = 'block';
    signupWrapper.style.display = 'block';

    if (originalLoginErrorVisible) loginError.classList.add('visible');
    else loginError.classList.remove('visible');
    
    if (originalSignupErrorVisible) signupError.classList.add('visible');
    else signupError.classList.remove('visible');

    // Force reflow
    loginWrapper.offsetHeight;
    signupWrapper.offsetHeight;

    loginHeight = loginWrapper.offsetHeight;
    signupHeight = signupWrapper.offsetHeight;

    loginWrapper.style.display = originalDisplayLogin;
    signupWrapper.style.display = originalDisplaySignup;
    
    if (originalLoginErrorVisible) loginError.classList.add('visible');
    else loginError.classList.remove('visible');
    
    if (originalSignupErrorVisible) signupError.classList.add('visible');
    else signupError.classList.remove('visible');
}

// Animate the wrapper (slide‑up)
function animateWrapperIn(wrapper) {
    if (animationInProgress) return;
    animationInProgress = true;
    wrapper.classList.add('animate-in');

    const onAnimationEnd = () => {
        wrapper.classList.remove('animate-in');
        animationInProgress = false;
        wrapper.removeEventListener('animationend', onAnimationEnd);
    };
    wrapper.addEventListener('animationend', onAnimationEnd, { once: true });
}

// Switch tabs with smooth height and fade
function switchToForm(targetWrapper) {
    const currentWrapper = loginWrapper.style.display === 'block' ? loginWrapper : signupWrapper;
    if (currentWrapper === targetWrapper) return;

    // Remove any ongoing error transition class
    formsWrapper.classList.remove('error-height-transition');
    if (switchTimeout) clearTimeout(switchTimeout);

    measureHeights();

    const currentHeight = formsWrapper.offsetHeight;
    const targetHeight = targetWrapper === loginWrapper ? loginHeight : signupHeight;

    formsWrapper.style.height = currentHeight + 'px';
    formsWrapper.offsetHeight; // force reflow
    formsWrapper.style.height = targetHeight + 'px';

    currentWrapper.classList.add('fade-out');

    switchTimeout = setTimeout(() => {
        currentWrapper.style.display = 'none';
        currentWrapper.classList.remove('fade-out');

        targetWrapper.style.display = 'block';
        
        // Clear errors on the target form
        if (targetWrapper === loginWrapper) {
            loginError.classList.remove('visible');
            loginError.textContent = '';
        } else {
            signupError.classList.remove('visible');
            signupError.textContent = '';
        }
        
        animateWrapperIn(targetWrapper);

        setTimeout(() => {
            if (targetWrapper === loginWrapper) loginUsername.focus();
            else signupUsername.focus();
        }, 100);

        const onHeightTransitionEnd = () => {
            formsWrapper.style.height = '';
            formsWrapper.removeEventListener('transitionend', onHeightTransitionEnd);
        };
        formsWrapper.addEventListener('transitionend', onHeightTransitionEnd, { once: true });

        switchTimeout = null;
    }, 250);
}

function showLogin() {
    loginTab.classList.add('active');
    signupTab.classList.remove('active');

    if (signupUsername.value) loginUsername.value = signupUsername.value;
    if (signupPassword.value) loginPassword.value = signupPassword.value;

    switchToForm(loginWrapper);
}

function showSignup() {
    signupTab.classList.add('active');
    loginTab.classList.remove('active');

    if (loginUsername.value) signupUsername.value = loginUsername.value;
    if (loginPassword.value) {
        signupPassword.value = loginPassword.value;
        signupConfirmPassword.value = loginPassword.value;
    }

    switchToForm(signupWrapper);
}

loginTab.addEventListener('click', showLogin);
signupTab.addEventListener('click', showSignup);

// --- Initial load (no animation) ---
loginWrapper.style.display = 'block';
signupWrapper.style.display = 'none';
measureHeights();
formsWrapper.style.height = loginHeight + 'px';
// Removed animateWrapperIn(loginWrapper) to prevent initial slide‑up
setTimeout(() => loginUsername.focus(), 100);

// --- Error handling with smooth height transitions (fixed) ---
function showError(element, message) {
    element.textContent = message;

    formsWrapper.classList.add('error-height-transition');

    const currentHeight = formsWrapper.offsetHeight;
    formsWrapper.style.height = currentHeight + 'px';
    formsWrapper.offsetHeight; // force reflow

    element.classList.add('visible');

    // Temporarily remove fixed height to measure natural height
    formsWrapper.style.height = '';
    const naturalHeight = formsWrapper.offsetHeight;
    formsWrapper.style.height = currentHeight + 'px';
    formsWrapper.offsetHeight;

    requestAnimationFrame(() => {
        formsWrapper.style.height = naturalHeight + 'px';

        const onTransitionEnd = () => {
            formsWrapper.classList.remove('error-height-transition');
            formsWrapper.style.height = '';
            formsWrapper.removeEventListener('transitionend', onTransitionEnd);
        };
        formsWrapper.addEventListener('transitionend', onTransitionEnd, { once: true });

        setTimeout(() => {
            if (formsWrapper.classList.contains('error-height-transition')) {
                formsWrapper.classList.remove('error-height-transition');
                formsWrapper.style.height = '';
            }
        }, 500);
    });
}

function clearError(element) {
    if (!element.classList.contains('visible')) return;

    formsWrapper.classList.add('error-height-transition');

    const currentHeight = formsWrapper.offsetHeight;
    formsWrapper.style.height = currentHeight + 'px';
    formsWrapper.offsetHeight;

    element.classList.remove('visible');
    element.textContent = '';

    formsWrapper.style.height = '';
    const naturalHeight = formsWrapper.offsetHeight;
    formsWrapper.style.height = currentHeight + 'px';
    formsWrapper.offsetHeight;

    requestAnimationFrame(() => {
        formsWrapper.style.height = naturalHeight + 'px';

        const onTransitionEnd = () => {
            formsWrapper.classList.remove('error-height-transition');
            formsWrapper.style.height = '';
            formsWrapper.removeEventListener('transitionend', onTransitionEnd);
        };
        formsWrapper.addEventListener('transitionend', onTransitionEnd, { once: true });

        setTimeout(() => {
            if (formsWrapper.classList.contains('error-height-transition')) {
                formsWrapper.classList.remove('error-height-transition');
                formsWrapper.style.height = '';
            }
        }, 500);
    });
}

// --- Form submissions ---
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = loginUsername.value.trim();
    const password = loginPassword.value;
    if (!username || !password) {
        showError(loginError, 'Username and password required');
        return;
    }
    clearError(loginError);
    loginBtn.disabled = true;
    loginBtn.textContent = 'Logging in...';
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (response.ok) {
            window.location.href = '/chat';
        } else {
            showError(loginError, data.error || 'Login failed');
            loginBtn.disabled = false;
            loginBtn.textContent = 'Login';
        }
    } catch (err) {
        showError(loginError, 'Network error');
        loginBtn.disabled = false;
        loginBtn.textContent = 'Login';
    }
});

signupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = signupUsername.value.trim();
    const password = signupPassword.value;
    const confirmPassword = signupConfirmPassword.value;

    if (!username || !password || !confirmPassword) {
        showError(signupError, 'All fields are required');
        return;
    }
    if (password.length < 6) {
        showError(signupError, 'Password must be at least 6 characters');
        return;
    }
    if (password !== confirmPassword) {
        showError(signupError, 'Passwords do not match');
        return;
    }

    clearError(signupError);
    signupBtn.disabled = true;
    signupBtn.textContent = 'Signing up...';
    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (response.ok) {
            const loginResponse = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            if (loginResponse.ok) {
                window.location.href = '/chat';
            } else {
                window.location.href = '/?username=' + encodeURIComponent(username);
            }
        } else {
            showError(signupError, data.error || 'Signup failed');
            signupBtn.disabled = false;
            signupBtn.textContent = 'Sign Up';
        }
    } catch (err) {
        showError(signupError, 'Network error');
        signupBtn.disabled = false;
        signupBtn.textContent = 'Sign Up';
    }
});