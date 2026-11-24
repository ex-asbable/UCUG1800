const { contextBridge, ipcRenderer } = require('electron')

const preferences = new Map(Object.entries(ipcRenderer.sendSync('tutor:preferences')))
contextBridge.exposeInMainWorld('tutorDesktop', {
  remembered: (key) => preferences.get(key) ?? null,
  remember: (key, value) => {
    if (value === null) preferences.delete(key)
    else preferences.set(key, value)
    ipcRenderer.send('tutor:remember', key, value)
  },
  saveMarkdown: (filename, markdown) => ipcRenderer.invoke('tutor:save-markdown', filename, markdown),
  updates: {
    status: () => ipcRenderer.invoke('tutor:update-status'),
    check: () => ipcRenderer.invoke('tutor:update-check'),
    install: () => ipcRenderer.invoke('tutor:update-install'),
    onStatus: (callback) => {
      const listener = (_event, status) => callback(status)
      ipcRenderer.on('tutor:update-status', listener)
      return () => ipcRenderer.removeListener('tutor:update-status', listener)
    },
  },
})
