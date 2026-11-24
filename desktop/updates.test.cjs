const assert = require('node:assert/strict')
const { createHash } = require('node:crypto')
const { mkdtemp, readFile, rm } = require('node:fs/promises')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const test = require('node:test')
const { DesktopUpdater } = require('./updates.cjs')

const repository = 'https://github.com/ex-asbable/UCUG1800'
const installer = Buffer.from('installer fixture')
const digest = createHash('sha256').update(installer).digest('hex')
const newVersion = '0.10.0'
const assetName = 'AI-Tutor-Setup-' + newVersion + '-x64.exe'
const url = repository + '/releases/download/v' + newVersion + '/' + assetName

function release(overrides) {
  return Response.json({
    tag_name: 'v' + newVersion,
    draft: false,
    prerelease: false,
    assets: [{ name: assetName, state: 'uploaded', size: installer.length, digest: 'sha256:' + digest,
      browser_download_url: url }],
    ...overrides,
  })
}

test('checks the configured GitHub release and compares versions numerically', async () => {
  let overrides
  const updater = new DesktopUpdater({
    version: '0.9.0', directory: tmpdir(), onStatus: () => {},
    launchInstaller: () => assert.fail('Checking must never start an installer'),
    request: async (endpoint) => {
      assert.equal(endpoint, 'https://api.github.com/repos/ex-asbable/UCUG1800/releases/latest')
      return release(overrides)
    },
  })
  assert.equal((await updater.check()).availableVersion, newVersion)
  for (overrides of [{ tag_name: 'v0.9.0' }, { tag_name: 'v0.8.1' }, { draft: true }, { prerelease: true }]) {
    assert.equal((await updater.check()).phase, 'current')
  }
  overrides = { assets: [{ name: assetName, browser_download_url: url, state: 'uploaded', size: installer.length }] }
  assert.equal((await updater.check()).error, 'update_asset_missing')
})

test('verifies GitHub download before launch and allows retry after corruption', async (t) => {
  const directory = await mkdtemp(join(tmpdir(), 'ai-tutor-update-test-'))
  t.after(() => rm(directory, { recursive: true }))
  let installs = 0
  let body = Buffer.alloc(installer.length)
  const phases = []
  const download = 'https://release-assets.githubusercontent.com/mock-asset'
  const updater = new DesktopUpdater({
    version: '0.1.0', directory, onStatus: (status) => phases.push(status.phase),
    launchInstaller: async (filename) => {
      assert.deepEqual(await readFile(filename), installer)
      installs += 1
    },
    request: async (address, options) => {
      if (address.startsWith('https://api.github.com/')) return release()
      assert.equal(options.redirect, 'manual')
      if (address === url) return Response.redirect(download)
      assert.equal(address, download)
      return new Response(body)
    },
  })
  await updater.check()
  assert.equal((await updater.install()).error, 'update_verification_failed')
  assert.equal(installs, 0)
  await assert.rejects(readFile(updater.installer), { code: 'ENOENT' })
  body = installer
  await updater.check()
  const first = updater.install()
  assert.equal((await updater.install()).phase, 'downloading')
  assert.equal((await first).phase, 'installing')
  assert.equal(installs, 1)
  assert.ok(phases.includes('available'))
})
