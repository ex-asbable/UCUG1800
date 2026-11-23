import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type Locale, type ModelEfforts, type ModelOption, type ReasoningEffort, type Runtime } from './api'
import { explain, type Copy } from './copy'
import { Modal } from './components'

const defaultApiUrl = 'https://api.openai.com/v1'
const codexQuery = { provider: 'codex_cli' } as const
type ApiQuery = { provider: 'api'; apiBaseUrl: string; apiKey: string }
type Query = ApiQuery | typeof codexQuery
type ModelCatalog = { models: ModelOption[]; codexVersion?: string | null; codexExecutable?: string }
type Catalog = ModelCatalog & { query: Query; revision: number; error: string }

function requestError(problem: unknown, updateRequired = false) {
  if (!(problem instanceof ApiError)) return 'connection_error'
  return updateRequired && problem.status === 404 ? 'runtime_update_required' : problem.code
}

const effortLabels: Record<ReasoningEffort, keyof Copy> = {
  none: 'effortNone',
  minimal: 'effortMinimal',
  low: 'effortLow',
  medium: 'effortMedium',
  high: 'effortHigh',
  xhigh: 'effortExtraHigh',
  max: 'effortMax',
  ultra: 'effortUltra',
}

export function ModelSettings({ runtime, locale, t, close, saved }: {
  runtime: Runtime; locale: Locale; t: Copy; close: () => void; saved: (status: Runtime) => void
}) {
  const [backend, setBackend] = useState(runtime.provider)
  const [selection, setSelection] = useState({
    api: { model: runtime.apiModel ?? '', effort: runtime.apiReasoningEffort ?? null },
    codex_cli: { model: runtime.codexModel ?? '', effort: runtime.codexReasoningEffort ?? null },
  })
  const [url, setUrl] = useState(runtime.apiBaseUrl ?? defaultApiUrl)
  const [key, setKey] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [apiQuery, setApiQuery] = useState<ApiQuery | null>(() => runtime.apiKeyConfigured
    ? { provider: 'api', apiBaseUrl: runtime.apiBaseUrl ?? defaultApiUrl, apiKey: '' }
    : null)
  const [revision, setRevision] = useState(0)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [effortResult, setEffortResult] = useState<{ model: ModelOption; details?: ModelEfforts; error?: string } | null>(null)
  const query = backend === 'api' ? apiQuery : codexQuery
  const currentCatalog = query && catalog?.query === query && catalog.revision === revision ? catalog : null
  const models = currentCatalog?.models ?? []
  const loadingCatalog = !!query && !currentCatalog
  const { model, effort } = selection[backend]
  const modelId = models.some((item) => item.id === model) ? model : ''
  const defaultModel = backend === 'codex_cli' ? models.find((item) => item.isDefault) : undefined
  const selectedModel = models.find((item) => item.id === modelId) ?? defaultModel
  const fetchedEffort = effortResult?.model === selectedModel ? effortResult : null
  const details = fetchedEffort?.details ?? selectedModel
  const effortOptions = details?.reasoningEfforts ?? []
  const activeEffort = effort && effortOptions.includes(effort) ? effort : null
  const lookingUpEffort = backend === 'api' && !!selectedModel && selectedModel.reasoningEfforts === null && !fetchedEffort
  const canApply = !!currentCatalog?.models.length && (backend === 'codex_cli' || !!modelId)
  const currentError = error || (backend === runtime.provider ? runtime.error : null)

  useEffect(() => {
    if (!query) return
    const controller = new AbortController()
    api<ModelCatalog>('/runtime/models', 'POST', query, controller.signal).then((result) => {
      if (!controller.signal.aborted) setCatalog({ ...result, query, revision, error: '' })
    }).catch((problem) => {
      if (!controller.signal.aborted) setCatalog({ query, revision, models: [], error: requestError(problem, true) })
    })
    return () => controller.abort()
  }, [query, revision])

  useEffect(() => {
    if (!query || query.provider !== 'api' || !selectedModel || selectedModel.reasoningEfforts !== null) return
    const controller = new AbortController()
    api<ModelEfforts>('/runtime/model-efforts', 'POST', {
      ...query, model: selectedModel.id,
    }, controller.signal).then((details) => {
      if (!controller.signal.aborted) setEffortResult({ model: selectedModel, details })
    }).catch((problem) => {
      if (!controller.signal.aborted) setEffortResult({ model: selectedModel, error: requestError(problem, true) })
    })
    return () => controller.abort()
  }, [query, selectedModel])

  function updateSelection(patch: Partial<(typeof selection)[Runtime['provider']]>) {
    setSelection((values) => ({ ...values, [backend]: { ...values[backend], ...patch } }))
  }

  function refreshModels() {
    if (backend === 'api') setApiQuery({ provider: 'api', apiBaseUrl: url, apiKey: key })
    setRevision((value) => value + 1)
    setError('')
  }

  async function apply(event: FormEvent) {
    event.preventDefault()
    if (saving || !canApply || loadingCatalog || lookingUpEffort) return
    setSaving(true)
    setError('')
    try {
      const status = await api<Runtime>('/runtime/settings', 'PATCH', backend === 'api'
        ? { provider: backend, apiModel: modelId, apiReasoningEffort: activeEffort, apiBaseUrl: url, apiKey: key }
        : { provider: backend, codexModel: modelId, codexReasoningEffort: activeEffort })
      saved(status)
    } catch (problem) {
      setError(requestError(problem, true))
    } finally {
      setSaving(false)
    }
  }

  return <Modal title={t.runtimeSettings} close={saving ? undefined : close} closeLabel={t.close}>
    <form className="runtime-form" onSubmit={(event) => void apply(event)}>
      <label className="field-label">{t.runtime}
        <select value={backend} onChange={(event) => { setBackend(event.target.value as Runtime['provider']); setError('') }}>
          <option value="codex_cli">Codex CLI</option>
          <option value="api">{t.modelApi}</option>
        </select>
      </label>
      {backend === 'api' && <>
        <label className="field-label">{t.apiBaseUrl}
          <input type="url" value={url} maxLength={1600} autoComplete="off" required
            onChange={(event) => { setUrl(event.target.value); setApiQuery(null) }} />
        </label>
        <label className="field-label">{t.apiKey}
          <input type="password" value={key} maxLength={4096} autoComplete="new-password"
            placeholder={runtime.apiKeyConfigured ? t.apiKeyConfigured : undefined}
            onChange={(event) => { setKey(event.target.value); setApiQuery(null) }} />
        </label>
      </>}
      <div className="model-picker-header">
        {backend === 'codex_cli' && currentCatalog?.codexVersion && (
          <small className="model-picker-version" title={currentCatalog.codexExecutable}>
            Codex CLI {currentCatalog.codexVersion}
          </small>
        )}
        <button type="button" className="text-button" onClick={refreshModels} disabled={loadingCatalog || saving}>
          {loadingCatalog ? t.loadingModels : t.refreshModels}
        </button>
        {loadingCatalog && <span role="status" className="visually-hidden">{t.loadingModels}</span>}
      </div>
      {currentCatalog?.error && <p className="warning-banner" role="alert">{explain(currentCatalog.error, locale)}</p>}
      {currentCatalog && !currentCatalog.error && !models.length && <p className="muted">{t.noModels}</p>}
      {!query && <p className="muted">{t.loadApiModels}</p>}
      <label className="field-label">{t.modelId}
        <select value={modelId} disabled={!models.length || saving} required={backend === 'api'}
          onChange={(event) => updateSelection({ model: event.target.value, effort: null })}>
          <option value="" disabled={backend === 'api'}>
            {backend === 'api' ? t.chooseModel : defaultModel ? t.modelDefault + ' · ' + defaultModel.name : t.modelDefault}
          </option>
          {models.map((item) => <option key={item.id} value={item.id}>{item.name === item.id ? item.id : item.name + ' · ' + item.id}</option>)}
        </select>
      </label>
      <label className="field-label">{t.reasoningEffort}
        <select value={activeEffort ?? ''} disabled={!selectedModel || lookingUpEffort || saving}
          onChange={(event) => updateSelection({ effort: (event.target.value || null) as ReasoningEffort | null })}>
          <option value="">{t.modelDefault}{details?.defaultReasoningEffort ? ' · ' + t[effortLabels[details.defaultReasoningEffort]] : ''}</option>
          {effortOptions.map((value) => <option key={value} value={value}>{t[effortLabels[value]]}</option>)}
        </select>
      </label>
      {lookingUpEffort && <p className="muted" role="status">{t.loadingEfforts}</p>}
      {fetchedEffort?.error && <p className="warning-banner" role="alert">{explain(fetchedEffort.error, locale)}</p>}
      {selectedModel && !lookingUpEffort && !fetchedEffort?.error && !effortOptions.length && <p className="muted">{t.defaultEffortOnly}</p>}
      <p className="muted">{backend === 'api' ? t.apiKeyLifetime : t.modelSettingsLifetime}</p>
      {currentError && <div className="warning-banner" role="alert">
        {explain(currentError, locale)}
      </div>}
      <div className="modal-footer">
        <button className="button secondary" type="button" disabled={saving} onClick={close}>{t.cancel}</button>
        <button className="button primary" disabled={saving || !canApply || loadingCatalog || lookingUpEffort}>
          {saving ? t.applying : t.apply}
        </button>
      </div>
    </form>
  </Modal>
}
