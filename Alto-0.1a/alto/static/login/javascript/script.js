const loginTab = document.getElementById('loginTab');
const signupTab = document.getElementById('signupTab');
const loginForm = document.getElementById('loginForm');
const signupForm = document.getElementById('signupForm');
const loginUsername = document.getElementById('loginUsername');
const loginPassword = document.getElementById('loginPassword');
const signupUsername = document.getElementById('signupUsername');
const signupPassword = document.getElementById('signupPassword');
const signupConfirmPassword = document.getElementById('signupConfirmPassword');
const loginBtn = document.getElementById('loginBtn');
const signupBtn = document.getElementById('signupBtn');
const loginError = document.getElementById('loginError');
const signupError = document.getElementById('signupError');

// Persist values when switching tabs
loginTab.addEventListener('click', () => {
    loginTab.classList.add('active');
    signupTab.classList.remove('active');
    loginForm.style.display = 'flex';
    signupForm.style.display = 'none';
    loginError.textContent = '';
    signupError.textContent = '';
    // Copy signup values to login if they exist
    if (signupUsername.value) loginUsername.value = signupUsername.value;
    if (signupPassword.value) loginPassword.value = signupPassword.value;
    // Focus username field to help password managers
    setTimeout(() => loginUsername.focus(), 100);
});

signupTab.addEventListener('click', () => {
    signupTab.classList.add('active');
    loginTab.classList.remove('active');
    signupForm.style.display = 'flex';
    loginForm.style.display = 'none';
    loginError.textContent = '';
    signupError.textContent = '';
    // Copy login values to signup if they exist
    if (loginUsername.value) signupUsername.value = loginUsername.value;
    if (loginPassword.value) {
        signupPassword.value = loginPassword.value;
        signupConfirmPassword.value = loginPassword.value;
    }
    // Focus username field to help password managers
    setTimeout(() => signupUsername.focus(), 100);
});

// Handle login form submission
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = loginUsername.value.trim();
    const password = loginPassword.value;
    if (!username || !password) {
        loginError.textContent = 'Username and password required';
        return;
    }
    loginError.textContent = '';
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
            loginError.textContent = data.error || 'Login failed';
            loginBtn.disabled = false;
            loginBtn.textContent = 'Login';
        }
    } catch (err) {
        loginError.textContent = 'Network error';
        loginBtn.disabled = false;
        loginBtn.textContent = 'Login';
    }
});

// Handle signup form submission
signupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = signupUsername.value.trim();
    const password = signupPassword.value;
    const confirmPassword = signupConfirmPassword.value;
    
    if (!username || !password || !confirmPassword) {
        signupError.textContent = 'All fields are required';
        return;
    }
    if (password.length < 6) {
        signupError.textContent = 'Password must be at least 6 characters';
        return;
    }
    if (password !== confirmPassword) {
        signupError.textContent = 'Passwords do not match';
        return;
    }
    
    signupError.textContent = '';
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
            // Auto-login after signup - direct redirect instead of triggering login form
            const loginResponse = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            if (loginResponse.ok) {
                window.location.href = '/chat';
            } else {
                // If auto-login fails, redirect to login page with pre-filled username
                window.location.href = '/?username=' + encodeURIComponent(username);
            }
        } else {
            signupError.textContent = data.error || 'Signup failed';
            signupBtn.disabled = false;
            signupBtn.textContent = 'Sign Up';
        }
    } catch (err) {
        signupError.textContent = 'Network error';
        signupBtn.disabled = false;
        signupBtn.textContent = 'Sign Up';
    }
});