const { app, BrowserWindow, session, Menu } = require('electron');
const path = require('path');
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const fs = require('fs');

// ===== CONFIGURATION =====
const DEV_MODE = true;            // Set to false for production
const SERVER_PORT = 3000;        // Port for the local Express server
const BACKEND_URL = 'http://127.0.0.1:5000';   // Python backend

// ===== INIT =====
// Remove default menu bar (File, Edit, etc.)
Menu.setApplicationMenu(null);

// Path to the static files (inside Client folder)
const staticPath = path.join(__dirname, 'static');

// Create Express app
const expressApp = express();

// Logging middleware
expressApp.use((req, res, next) => {
    if (DEV_MODE) console.log(`[Express] ${req.method} ${req.url}`);
    next();
});

// ===== Serve static files (only local, no fallback) =====
expressApp.use('/static', (req, res, next) => {
    const requestedPath = req.path; // e.g., /chat/style/style.css
    const localFile = path.join(staticPath, requestedPath);
    fs.access(localFile, fs.constants.R_OK, (err) => {
        if (err) {
            if (DEV_MODE) console.error(`File not found: ${localFile}`);
            return res.status(404).send('File not found');
        }
        res.sendFile(localFile);
    });
});

// ===== Serve HTML pages (only local, no fallback) =====
function serveHtmlPage(htmlPath, res) {
    const localFile = path.join(staticPath, htmlPath);
    fs.access(localFile, fs.constants.R_OK, (err) => {
        if (err) {
            if (DEV_MODE) console.error(`Page not found: ${localFile}`);
            return res.status(404).send('Page not found');
        }
        res.sendFile(localFile);
    });
}

expressApp.get('/', (req, res) => serveHtmlPage('login/index.html', res));
expressApp.get('/chat', (req, res) => serveHtmlPage('chat/index.html', res));

// ===== Proxy API and chat POST requests to backend =====
const backendProxy = createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    logLevel: DEV_MODE ? 'debug' : 'silent',
    onError: (err, req, res) => {
        console.error('Proxy error:', err);
        res.status(503).json({ error: 'Backend unavailable' });
    }
});
expressApp.use('/api', backendProxy);
expressApp.use('/chat', backendProxy);   // only POST requests

// ===== Fallback for any other route =====
expressApp.get('*', (req, res) => {
    if (DEV_MODE) console.log(`No route for ${req.url}, serving 404`);
    res.status(404).send('Not found');
});

// ===== Start local server =====
const server = expressApp.listen(SERVER_PORT, () => {
    console.log(`Local server running at http://localhost:${SERVER_PORT}`);
});

// ===== Electron window =====
let mainWindow;

app.whenReady().then(async () => {
    // Check if user is already logged in (cookies persist)
    const cookies = await session.defaultSession.cookies.get({ url: `http://localhost:${SERVER_PORT}`, name: 'user_id' });
    const isLoggedIn = cookies.length > 0 && cookies[0].value;

    const startUrl = isLoggedIn
        ? `http://localhost:${SERVER_PORT}/chat`
        : `http://localhost:${SERVER_PORT}`;

    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
        },
        menu: null,
    });

    mainWindow.loadURL(startUrl);

    if (DEV_MODE) {
        mainWindow.webContents.openDevTools();
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
    server.close();
});