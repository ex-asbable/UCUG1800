const { app, BrowserWindow, dialog, ipcMain, session } = require('electron')
const { spawn, spawnSync } = require('node:child_process')
const { randomBytes } = require('node:crypto')
const { readFileSync, mkdirSync, writeFileSync, renameSync } = require('node:fs')
const { writeFile } = require('node:fs/promises')
const { basename, join, resolve } = require('node:path')
const { createInterface } = require('node:readline')
const { setTimeout: delay } = require('node:timers/promises')

const root = join(__dirname, '..')
const token = randomBytes(32).toString('hex')
const originalPdf = /^\/api\/v1\/courses\/[\w-]+\/materials\/[\w-]+\/pdf$/
let backend
let origin
let mainWindow
let shuttingDown = false

async function startBackend(dataDirectory) {
  const executable = app.isPackaged
    ? join(process.resourcesPath, 'backend', 'ai-tutor-service.exe')
    : join(root, '.venv', 'Scripts', 'python.exe')
  const args = app.isPackaged ? [] : ['-m', 'tutor.desktop']
  backend = spawn(executable, args, {
    cwd: app.isPackaged ? dataDirectory : root,
    env: { ...process.env, AI_TUTOR_DATA_DIR: dataDirectory, AI_TUTOR_DESKTOP_TOKEN: token },
    windowsHide: true,
  })
  backend.stderr.on('data', (data) => process.stderr.write(data))
  const port = await new Promise((resolve, reject) => {
    const output = createInterface({ input: backend.stdout })
    const timer = setTimeout(() => { output.close(); reject(new Error('Local service startup timed out.')) }, 30000)
    output.once('line', (line) => {
      clearTimeout(timer)
      output.close()
      const port = Number(line)
      if (Number.isInteger(port) && port > 0 && port <= 65535) resolve(port)
      else reject(new Error('Local service did not return a valid port.'))
    })
    backend.once('error', (error) => { clearTimeout(timer); output.close(); reject(error) })
    backend.once('exit', () => {
      clearTimeout(timer)
      output.close()
      reject(new Error('Local service stopped during startup.'))
      if (mainWindow && !shuttingDown) {
        dialog.showErrorBox('AI Tutor', '本机服务已退出，请重新打开 AI Tutor。\nThe local service stopped. Reopen AI Tutor to continue.')
        app.quit()
      }
    })
  })
  origin = 'http://127.0.0.1:' + port
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const ready = await fetch(origin + '/', {
      headers: { 'X-AI-Tutor-Desktop': token },
      signal: AbortSignal.timeout(500),
    }).then((response) => response.ok, () => false)
    if (ready) return
    if (backend.exitCode !== null) break
    await delay(250)
  }
  throw new Error('Local service or the application files could not be loaded.')
}

function configureWindow(window, allowPdf = false) {
  const contents = window.webContents
  contents.on('will-navigate', (event) => event.preventDefault())
  contents.on('will-redirect', (event) => event.preventDefault())
  contents.setWindowOpenHandler(({ url }) => {
    const target = new URL(url)
    if (allowPdf && target.origin === origin && originalPdf.test(target.pathname)) {
      const pdfWindow = new BrowserWindow({
        width: 950, height: 800, title: 'AI Tutor',
        webPreferences: { sandbox: true, plugins: true },
      })
      configureWindow(pdfWindow)
      void pdfWindow.loadURL(target.href).catch(() => pdfWindow.close())
    }
    return { action: 'deny' }
  })
  window.setMenuBarVisibility(false)
}

function configureBridge(dataDirectory) {
  const file = join(dataDirectory, 'desktop-preferences.json')
  let preferences
  try {
    const saved = JSON.parse(readFileSync(file, 'utf8'))
    preferences = Object.assign(Object.create(null), saved)
  } catch {
    preferences = Object.create(null)
  }

  function allowed(event) {
    return !!mainWindow && event.sender === mainWindow.webContents &&
      event.senderFrame === mainWindow.webContents.mainFrame && event.senderFrame.url === origin + '/'
  }

  ipcMain.on('tutor:preferences', (event) => {
    event.returnValue = allowed(event) ? { ...preferences } : {}
  })
  ipcMain.on('tutor:remember', (event, key, value) => {
    if (!allowed(event) || typeof key !== 'string' || !/^[\w.-]{1,120}$/.test(key)) return
    if (value === null) delete preferences[key]
    else if (typeof value === 'string' && value.length <= 24000) preferences[key] = value
    else return
    try {
      writeFileSync(file + '.tmp', JSON.stringify(preferences), 'utf8')
      renameSync(file + '.tmp', file)
    } catch (error) {
      console.error('Could not save app preferences:', error.code)
    }
  })
  ipcMain.handle('tutor:save-markdown', async (event, name, markdown) => {
    if (!allowed(event) || typeof markdown !== 'string' || markdown.length > 50000 ||
        typeof name !== 'string' || !name.endsWith('.md') || basename(name) !== name || name.length > 120) {
      throw new Error('Invalid Markdown export.')
    }
    const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
      defaultPath: join(app.getPath('documents'), name),
      filters: [{ name: 'Markdown', extensions: ['md'] }],
    })
    if (canceled || !filePath) return false
    await writeFile(filePath, markdown, 'utf8')
    return true
  })
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.setAppUserModelId('io.github.exasbable.aitutor')
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  })
  app.on('before-quit', () => {
    if (shuttingDown) return
    shuttingDown = true
    if (backend?.pid && backend.exitCode === null) {
      // Restart recovery requeues interrupted jobs, including those with a model subprocess.
      const command = join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'taskkill.exe')
      spawnSync(command, ['/pid', String(backend.pid), '/t', '/f'], { windowsHide: true, timeout: 4000 })
      backend.stdin.end()
    }
  })
  app.on('window-all-closed', () => app.quit())
  app.whenReady().then(async () => {
    const dataDirectory = resolve(process.env.AI_TUTOR_DATA_DIR || join(app.getPath('userData'), 'data'))
    mkdirSync(dataDirectory, { recursive: true })
    await startBackend(dataDirectory)
    const browserSession = session.defaultSession
    browserSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
    browserSession.setPermissionCheckHandler(() => false)
    browserSession.webRequest.onBeforeSendHeaders({ urls: [origin + '/*'] }, (details, callback) => {
      callback({ requestHeaders: { ...details.requestHeaders, 'X-AI-Tutor-Desktop': token } })
    })
    configureBridge(dataDirectory)
    mainWindow = new BrowserWindow({
      width: 1360, height: 900, minWidth: 700, minHeight: 550, show: false,
      backgroundColor: '#f7f3fb', icon: join(__dirname, 'icon.ico'),
      webPreferences: { preload: join(__dirname, 'preload.cjs'), sandbox: true },
    })
    configureWindow(mainWindow, true)
    mainWindow.once('ready-to-show', () => mainWindow.show())
    mainWindow.on('closed', () => {
      mainWindow = undefined
      app.quit()
    })
    await mainWindow.loadURL(origin + '/')
  }).catch((error) => {
    dialog.showErrorBox('AI Tutor', '无法启动 AI Tutor / Could not start AI Tutor\n\n' + error.message)
    app.quit()
  })
}
