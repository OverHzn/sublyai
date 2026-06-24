const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

let mainWindow = null;
let pythonProc = null;

app.setPath('userData', path.join(app.getPath('appData'), 'SublyAI'));

function getProjectRoot() {
  if (app.isPackaged) {
    const bundled = path.join(process.resourcesPath, 'sublyai');
    if (fs.existsSync(path.join(bundled, 'app.py'))) return bundled;
    const portable = path.join(path.dirname(process.execPath), 'sublyai');
    if (fs.existsSync(path.join(portable, 'app.py'))) return portable;
    return path.join(path.dirname(process.execPath));
  }
  return path.join(__dirname, '..');
}

function getUserDataDirs() {
  const base = app.getPath('userData');
  return {
    downloads: path.join(base, 'downloads'),
    outputs: path.join(base, 'outputs'),
    jobs: path.join(base, 'jobs'),
    config: path.join(base, 'config'),
  };
}

function ensureDataDirs(dirs) {
  for (const dir of Object.values(dirs)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function getPythonExe(root) {
  const candidates = [
    path.join(root, '.venv', 'Scripts', 'python.exe'),
    path.join(path.dirname(process.execPath), '.venv', 'Scripts', 'python.exe'),
    path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe'),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function detectStartupError(text) {
  if (/ffmpeg tidak ditemukan|ffmpeg is not installed/i.test(text)) {
    return 'ffmpeg tidak ditemukan di PATH. Install ffmpeg lalu jalankan ulang.';
  }
  return null;
}

function startPythonServer(root, pythonExe) {
  return new Promise((resolve, reject) => {
    const script = path.join(root, 'run_server.py');
    const dataDirs = getUserDataDirs();
    ensureDataDirs(dataDirs);

    const env = {
      ...process.env,
      SUBLYAI_NO_BROWSER: '1',
      PYTHONUNBUFFERED: '1',
      PYTHONUTF8: '1',
      SUBLYAI_DOWNLOADS_DIR: dataDirs.downloads,
      SUBLYAI_OUTPUTS_DIR: dataDirs.outputs,
      SUBLYAI_JOBS_DIR: dataDirs.jobs,
      SUBLYAI_CONFIG_DIR: dataDirs.config,
    };

    let portKnown = false;
    let settled = false;
    let stdoutBuf = '';
    let stderrBuf = '';

    pythonProc = spawn(pythonExe, [script], {
      cwd: root,
      env,
      windowsHide: true,
    });

    const fail = (err) => {
      if (settled) return;
      settled = true;
      reject(err);
    };

    const onPort = async (port) => {
      if (portKnown) return;
      portKnown = true;
      try {
        await waitForServer(port);
        if (!settled) {
          settled = true;
          resolve(port);
        }
      } catch (err) {
        fail(err);
      }
    };

    const inspectOutput = (text) => {
      const startupError = detectStartupError(text);
      if (startupError) fail(new Error(startupError));
    };

    pythonProc.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      process.stdout.write(text);
      stdoutBuf += text;
      inspectOutput(stdoutBuf);
      const match = stdoutBuf.match(/SUBLYAI_PORT=(\d+)/);
      if (match) onPort(parseInt(match[1], 10));
    });

    pythonProc.stderr.on('data', (chunk) => {
      const text = chunk.toString();
      process.stderr.write(text);
      stderrBuf += text;
      inspectOutput(stderrBuf);
    });

    pythonProc.on('exit', (code) => {
      if (code !== 0 && code !== null) {
        const tail = (stderrBuf || stdoutBuf).trim().slice(-400);
        const detail = tail ? `\n\n${tail}` : '';
        if (!settled) {
          fail(new Error(`Python server berhenti (code ${code}). Cek ffmpeg & .venv sudah terinstall.${detail}`));
        }
        if (mainWindow && !mainWindow.isDestroyed()) {
          dialog.showErrorBox(
            'SublyAI Server Error',
            `Python server berhenti (code ${code}).\nCek ffmpeg & .venv sudah terinstall.${detail}`
          );
        }
      }
    });

    setTimeout(() => {
      if (!portKnown) {
        fail(new Error('Server tidak mengirim port. Cek .venv & dependencies.'));
      }
    }, 90000);
  });
}

function waitForServer(port, maxAttempts = 120) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const tryOnce = () => {
      const req = http.get(`http://127.0.0.1:${port}/healthz`, (res) => {
        let body = '';
        res.on('data', (chunk) => {
          body += chunk.toString();
        });
        res.on('end', () => {
          if (res.statusCode !== 200) {
            retry();
            return;
          }
          try {
            const payload = JSON.parse(body);
            if (payload.ffmpeg === 'missing') {
              reject(new Error('ffmpeg tidak ditemukan di PATH. Install ffmpeg lalu jalankan ulang.'));
              return;
            }
          } catch (_) {
            // Legacy healthz without ffmpeg field — treat 200 as ready.
          }
          resolve();
        });
      });
      req.on('error', retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (++attempts >= maxAttempts) {
        reject(new Error('Server tidak merespons. Coba jalankan stop.bat lalu buka lagi.'));
        return;
      }
      setTimeout(tryOnce, 500);
    };
    tryOnce();
  });
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    title: `SublyAI — :${port}`,
    backgroundColor: '#020807',
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(`http://127.0.0.1:${port}`);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

async function boot() {
  const root = getProjectRoot();
  const pythonExe = getPythonExe(root);

  if (!pythonExe) {
    const setupHint = app.isPackaged
      ? 'Jalankan setup-app.bat di folder instalasi dulu.'
      : 'Jalankan setup-app.bat sekali untuk setup .venv.';
    dialog.showErrorBox(
      'Python tidak ditemukan',
      `Virtual environment (.venv) belum ada.\n\n${setupHint}`
    );
    app.quit();
    return;
  }

  if (!fs.existsSync(path.join(root, 'run_server.py'))) {
    dialog.showErrorBox('File hilang', `run_server.py tidak ada di:\n${root}`);
    app.quit();
    return;
  }

  try {
    const port = await startPythonServer(root, pythonExe);
    createWindow(port);
  } catch (err) {
    dialog.showErrorBox('Gagal start', err.message);
    killPython();
    app.quit();
  }
}

function killPython() {
  if (!pythonProc || pythonProc.killed) return;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(pythonProc.pid), '/f', '/t'], { windowsHide: true });
    } else {
      pythonProc.kill('SIGTERM');
    }
  } catch (_) {
    pythonProc.kill();
  }
  pythonProc = null;
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(boot);

  app.on('window-all-closed', () => {
    killPython();
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('before-quit', killPython);
}