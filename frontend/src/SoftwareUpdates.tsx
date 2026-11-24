import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import type { DesktopUpdate, Locale } from './api'
import { Modal } from './components'
import { explain, type Copy } from './copy'

export function SoftwareUpdates({ locale, t }: { locale: Locale; t: Copy }) {
  const updates = window.tutorDesktop?.updates
  const [status, setStatus] = useState<DesktopUpdate | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!updates) return
    let active = true
    let received = false
    const stop = updates.onStatus((next) => {
      received = true
      setStatus(next)
    })
    void updates.status().then((initial) => {
      if (active && !received) setStatus(initial)
    }).catch(() => {})
    return () => {
      active = false
      stop()
    }
  }, [updates])

  if (!updates || !status) return null
  const busy = status.phase === 'checking' || status.phase === 'downloading' || status.phase === 'installing'
  const canInstall = status.availableVersion && status.error !== 'update_verification_failed'
  const message = {
    idle: '',
    checking: t.updateChecking,
    current: t.updateCurrent,
    available: t.updateAvailable + ' · v' + status.availableVersion,
    downloading: t.updateDownloading + ' ' + status.progress + '%',
    installing: t.updateInstalling,
    error: status.error ? explain(status.error, locale) : '',
  }[status.phase]
  const run = (action: 'check' | 'install') => {
    void updates[action]().catch(() => {
      setStatus((current) => current && {
        ...current, phase: 'error', error: action === 'check' ? 'update_check_failed' : 'update_install_failed',
      })
    })
  }

  return <>
    <button className={'runtime' + (status.availableVersion ? ' update-available' : '')}
      aria-label={status.availableVersion ? t.updateAvailable : t.updates}
      title={status.availableVersion ? t.updateAvailable : t.updates}
      onClick={() => setOpen(true)}>
      <Download size={16} /><span>{status.availableVersion ? t.updateAvailable : t.updates}</span>
    </button>
    {open && <Modal title={t.updates} close={() => setOpen(false)} closeLabel={t.close}>
      <div className="update-panel">
        <p className="muted">{t.updateCurrentVersion} · v{status.currentVersion}</p>
        {message && <p role="status">{message}</p>}
        {status.phase === 'downloading' &&
          <progress className="update-progress" aria-label={t.updateDownloading} value={status.progress} max={100} />}
        <div className="modal-footer">
          <button className={canInstall ? 'button secondary' : 'button primary'} disabled={busy}
            onClick={() => run('check')}>{t.updateCheck}</button>
          {canInstall && <button className="button primary" disabled={busy}
            onClick={() => run('install')}>{t.updateInstall}</button>}
        </div>
      </div>
    </Modal>}
  </>
}
