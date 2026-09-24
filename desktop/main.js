const { app, BrowserWindow } = require("electron");
const path = require("path");
const http = require("http");
const fs = require("fs");
const { spawn } = require("child_process");

let backendProcess = null;
let staticServer = null;
let staticPort = null;

// The renderer only ever talks to loopback services, so system
// proxy auto-detection (WPAD/PAC) must never delay its first
// request: on misconfigured networks that resolution alone can
// stall Chromium for minutes before any window content loads.
app.commandLine.appendSwitch("no-proxy-server");

// Ports already present in the backend CORS allowlist
// (backend/main.py). Whichever one we bind gives the renderer an
// origin the backend accepts.
const ALLOWED_PORTS = [5177, 5174, 5173];

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

// In a packaged build the frontend bundle and the backend
// source tree are copied by electron-builder into
// <install>/resources/ (see "extraResources" in package.json).
// In development they stay as sibling directories of desktop/.
function frontendDistPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "frontend", "dist");
  }
  return path.join(__dirname, "..", "frontend", "dist");
}

function backendProjectRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend-project");
  }
  return path.join(__dirname, "..");
}

// Serve the bundle over loopback HTTP instead of file://: a
// file:// page sends Origin: null, which the backend CORS
// allowlist rejects, so login and every API call would fail.
function startStaticServer(distRoot) {
  return new Promise((resolve) => {
    const tryPort = (index) => {
      if (index >= ALLOWED_PORTS.length) {
        resolve(null);
        return;
      }

      const server = http.createServer((req, res) => {
        const urlPath = decodeURIComponent(
          (req.url || "/").split("?")[0]
        );

        const relative =
          urlPath === "/" ? "index.html" : urlPath.replace(/^\/+/, "");

        const filePath = path.resolve(distRoot, relative);

        if (!filePath.startsWith(distRoot + path.sep)) {
          res.writeHead(403);
          res.end();
          return;
        }

        fs.readFile(filePath, (error, content) => {
          if (error) {
            res.writeHead(404);
            res.end();
            return;
          }

          const type =
            MIME_TYPES[path.extname(filePath).toLowerCase()] ||
            "application/octet-stream";

          res.writeHead(200, { "Content-Type": type });
          res.end(content);
        });
      });

      server.on("error", () => tryPort(index + 1));

      server.listen(ALLOWED_PORTS[index], "127.0.0.1", () => {
        staticServer = server;
        staticPort = ALLOWED_PORTS[index];
        resolve(staticPort);
      });
    };

    tryPort(0);
  });
}

function startBackend() {
  backendProcess = spawn(
    "python",
    [
      "-m",
      "uvicorn",
      "backend.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8000",
    ],
    {
      cwd: backendProjectRoot(),
      windowsHide: true,
    }
  );

  backendProcess.on("error", (error) => {
    console.error("Failed to start ENMA backend:", error);
  });

  backendProcess.on("exit", (code, signal) => {
    console.log(`ENMA backend exited. code=${code}, signal=${signal}`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  let shown = false;

  const show = () => {
    if (shown) return;
    shown = true;
    win.show();
  };

  win.once("ready-to-show", show);

  // The window must open promptly even when the backend or the
  // provider is unavailable, so first paint must never be the
  // only thing that can reveal it: bounded fallback plus an
  // explicit failure path instead of an invisible app.
  setTimeout(show, 2000);

  win.webContents.once("did-fail-load", () => {
    console.error("ENMA frontend failed to load");
    show();
  });

  if (staticPort) {
    win.loadURL(`http://127.0.0.1:${staticPort}/`);
  } else {
    win.loadFile(path.join(frontendDistPath(), "index.html"));
  }
}

app.whenReady().then(async () => {
  await startStaticServer(frontendDistPath());

  createWindow();
  startBackend();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", () => {
  stopBackend();

  if (staticServer) {
    staticServer.close();
    staticServer = null;
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
