const { createHash } = require('node:crypto')
const { createWriteStream } = require('node:fs')
const { mkdir, rm } = require('node:fs/promises')
const { join } = require('node:path')
const { Readable, Transform } = require('node:stream')
const { pipeline } = require('node:stream/promises')

const repo = 'ex-asbable/UCUG1800'
const latestRelease = `https://api.github.com/repos/${repo}/releases/latest`
const githubHosts = new Set(['github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'])
const versionPattern = /^v?(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})$/
const digestPattern = /^sha256:([a-f0-9]{64})$/i

class UpdateError extends Error {}

function newerVersion(current, tag) {
  const installed = versionPattern.exec(current)?.slice(1).map(Number)
  const latest = versionPattern.exec(tag)?.slice(1).map(Number)
  if (!installed || !latest) return null
  const difference = latest.findIndex((part, index) => part !== installed[index])
  return difference >= 0 && latest[difference] > installed[difference] ? latest.join('.') : null
}

async function findUpdate(currentVersion, request) {
  const response = await request(latestRelease, {
    headers: { accept: 'application/vnd.github+json' },
    credentials: 'omit',
    redirect: 'error',
    signal: AbortSignal.timeout(15000),
  })
  if (!response.ok) throw new UpdateError('update_check_failed')
  const release = await response.json()
  const version = newerVersion(currentVersion, release.tag_name)
  if (release.draft || release.prerelease || !version) return null

  const name = `AI-Tutor-Setup-${version}-x64.exe`
  const url = `https://github.com/${repo}/releases/download/${release.tag_name}/${name}`
  const asset = release.assets?.find((item) =>
    item.name === name && item.state === 'uploaded' && item.browser_download_url === url)
  const sha256 = digestPattern.exec(asset?.digest)?.[1].toLowerCase()
  if (!sha256 || !Number.isSafeInteger(asset.size) || asset.size < 1 || asset.size > 2 ** 31) {
    throw new UpdateError('update_asset_missing')
  }
  return { version, url, size: asset.size, sha256 }
}

async function download(update, filename, request, progress) {
  const signal = AbortSignal.timeout(15 * 60 * 1000)
  let url = new URL(update.url)
  let response
  for (let redirects = 0; redirects <= 3; redirects += 1) {
    if (url.protocol !== 'https:' || !githubHosts.has(url.hostname) || url.port || url.username || url.password) {
      throw new UpdateError('update_download_failed')
    }
    response = await request(url.href, { credentials: 'omit', redirect: 'manual', signal })
    if (![301, 302, 303, 307, 308].includes(response.status)) break
    const location = response.headers.get('location')
    await response.body?.cancel()
    if (!location) throw new UpdateError('update_download_failed')
    url = new URL(location, url)
  }
  if (response.status !== 200 || !response.body) throw new UpdateError('update_download_failed')
  const digest = createHash('sha256')
  let bytes = 0
  const verify = new Transform({
    transform(chunk, _encoding, done) {
      bytes += chunk.length
      if (bytes > update.size) return done(new UpdateError('update_verification_failed'))
      digest.update(chunk)
      progress(Math.floor(100 * bytes / update.size))
      done(null, chunk)
    },
  })
  await pipeline(Readable.fromWeb(response.body), verify, createWriteStream(filename, { flags: 'wx' }), { signal })
  if (bytes !== update.size || digest.digest('hex') !== update.sha256) {
    throw new UpdateError('update_verification_failed')
  }
}

class DesktopUpdater {
  constructor({ version, directory, onStatus, launchInstaller, request = fetch }) {
    this.directory = directory
    this.installer = join(directory, 'installer.exe')
    this.update = null
    this.state = { phase: 'idle', currentVersion: version, availableVersion: null, progress: 0, error: null }
    this.onStatus = onStatus
    this.launchInstaller = launchInstaller
    this.request = request
  }

  get busy() {
    return ['checking', 'downloading', 'installing'].includes(this.state.phase)
  }

  setStatus(phase, { progress = 0, error = null } = {}) {
    this.state = { ...this.state, phase, availableVersion: this.update?.version ?? null, progress, error }
    this.onStatus(this.state)
  }

  async check() {
    if (this.busy) return this.state
    this.update = null
    this.setStatus('checking')
    try {
      this.update = await findUpdate(this.state.currentVersion, this.request)
      this.setStatus(this.update ? 'available' : 'current')
    } catch (error) {
      this.setStatus('error', { error: error instanceof UpdateError ? error.message : 'update_check_failed' })
    }
    return this.state
  }

  async install() {
    if (!this.update || this.busy) return this.state
    this.setStatus('downloading')
    let stage = 'update_download_failed'
    try {
      await mkdir(this.directory, { recursive: true })
      await this.cleanInstaller()
      await download(this.update, this.installer, this.request, (progress) => {
        if (progress > this.state.progress) this.setStatus('downloading', { progress })
      })
      stage = 'update_install_failed'
      this.setStatus('installing', { progress: 100 })
      await this.launchInstaller(this.installer)
    } catch (error) {
      await this.cleanInstaller().catch(() => {})
      this.setStatus('error', { error: error instanceof UpdateError ? error.message : stage })
    }
    return this.state
  }

  cleanInstaller() {
    return rm(this.installer, { force: true })
  }
}

module.exports = { DesktopUpdater }
