const { app, BrowserWindow, session, Menu } = require('electron');
const path = require('path');
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const fs = require('fs');

// ===== CONFIGURATION =====
const DEV_MODE = true;
const SERVER_PORT = 3000;
const BACKEND_URL = 'http://127.0.0.1:5000';

// ===== INIT =====
Menu.setApplicationMenu(null);

const staticPath = path.join(__dirname, 'static');
const expressApp = express();

// Logging middleware
expressApp.use((req, res, next) => {
    if (DEV_MODE) console.log(`[Express] ${req.method} ${req.url}`);
    next();
});

// Serve static files
expressApp.use('/static', (req, res, next) => {
    const localFile = path.join(staticPath, req.path);
    fs.access(localFile, fs.constants.R_OK, (err) => {
        if (err) {
            if (DEV_MODE) console.error(`File not found: ${localFile}`);
            return res.status(404).send('File not found');
        }
        res.sendFile(localFile);
    });
});

// Serve HTML pages
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

// ===== Proxy configuration =====
const backendProxy = createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    cookieDomainRewrite: '',       // Keep cookies for localhost
    logLevel: DEV_MODE ? 'debug' : 'silent',
    onError: (err, req, res) => {
        console.error('Proxy error:', err);
        if (!res.headersSent) {
            res.status(503).json({ error: 'Backend unavailable' });
        }
    },
    onProxyReq: (proxyReq, req, res) => {
        // Ensure cookies are forwarded
        if (req.headers.cookie) {
            proxyReq.setHeader('cookie', req.headers.cookie);
        }
    }
});

expressApp.use('/api', backendProxy);
expressApp.use('/chat', backendProxy);   // Proxy POST /chat

// Catch-all 404
expressApp.get('*', (req, res) => {
    if (DEV_MODE) console.log(`No route for ${req.url}, serving 404`);
    res.status(404).send('Not found');
});

// ===== Start Express server =====
const server = expressApp.listen(SERVER_PORT, () => {
    console.log(`Local server running at http://localhost:${SERVER_PORT}`);
});

// Keep server alive – do not close on window close
server.keepAliveTimeout = 0;
server.headersTimeout = 0;

// ===== Electron window =====
let mainWindow;

app.whenReady().then(async () => {
    // Check if user is already logged in using persistent session
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
        icon: path.join(__dirname, 'favicon.ico')
    });

    mainWindow.loadURL(startUrl);

    if (DEV_MODE) {
        mainWindow.webContents.openDevTools();
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
});

// Do not quit the app when all windows are closed (keep Express server running)
app.on('window-all-closed', () => {
    // On macOS, keep app running until user explicitly quits
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// Gracefully close the server when the app is quitting
app.on('before-quit', () => {
    server.close();
});