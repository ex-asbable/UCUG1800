export type Locale = 'zh-Hans' | 'en'
export type ChapterMode = 'knowledge' | 'file'
export type Format = 'choice' | 'text' | 'tex'
export type GapStatus = 'unassessed' | 'pending' | 'review_needed' | 'resolved' | 'not_confirmed'
export type Ref = { materialId: string; page: number }
export type Course = { id: string; name: string; outlineId: string | null }
export type ReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max' | 'ultra'
export type Runtime = {
  provider: 'api' | 'codex_cli'
  ready: boolean
  error: string | null
  apiModel?: string
  apiBaseUrl?: string
  apiKeyConfigured?: boolean
  apiReasoningEffort?: ReasoningEffort | null
  codexModel?: string
  codexReasoningEffort?: ReasoningEffort | null
}
export type ModelEfforts = {
  reasoningEfforts: ReasoningEffort[] | null
  defaultReasoningEffort: ReasoningEffort | null
}
export type ModelOption = ModelEfforts & { id: string; name: string; isDefault: boolean }
export type Job = {
  jobId: string
  kind: 'import' | 'folder' | 'start' | 'dialogue' | 'question' | 'evaluate' | 'guide'
  status: 'queued' | 'running' | 'ready' | 'failed'
  stage: 'queued' | 'parsing' | 'analyzing_images' | 'generating' | 'ready'
  error: string | null
}
export type ReviewGuide = { markdown: string; sources: Ref[] }
export type ImportIssue = { filename: string; code: string }
export type Material = {
  id: string
  filename: string
  status: 'queued' | 'parsing' | 'generating' | 'ready' | 'failed' | 'superseded' | 'attached'
  issue: string | null
  active: boolean
  pageCount: number
  requiresMultimodal: boolean
  unreadablePages: number[]
}
export type Catalog = { course: Course; materials: Material[]; jobs: Job[] }
export type Topic = {
  id: string
  materialId?: string
  parentId: string | null
  position: number
  title: string
  status?: GapStatus
  coverage: 'supported' | 'missing' | 'prerequisite'
  explanation: string
  opening: string
  sources: Ref[]
}
export type Gap = {
  id: string
  topicId: string
  sessionId: string
  description: string
  status: GapStatus
  reason: string | null
  trigger: string
  evidence?: string
  checkId?: string
}
export type ReviewGroup = { topic: Topic; count: number; gaps: Gap[] }
export type SessionItem = { id: string; topicId: string | null; updated: string; title: string | null }
export type CheckStatus = 'open' | 'submitted' | 'graded' | 'abandoned'
export type Session = {
  id: string
  outlineId: string
  topicId: string | null
  topic: Topic | null
  locale: Locale
  messages: { id: string; role: 'student' | 'tutor'; text: string; sources: Ref[] }[]
  gaps: Gap[]
  check: { id: string; status: CheckStatus } | null
  jobs: Job[]
}
export type Answer = string | Record<string, string>
export type Attempt = {
  id: string
  answer: Answer
  reason: string
  result: {
    correctness: 'correct' | 'incorrect' | 'uncertain'
    evidence: string
    feedback: string | null
    feedbackCode: string | null
    gapStatus: GapStatus | null
  } | null
}
export type Check = {
  id: string
  locale: Locale
  sessionId: string
  status: CheckStatus
  format: Format
  prompt: string
  requiresReason: boolean
  options: { id: string; text: string }[]
  fields: { id: string; label: string }[]
  attempt?: Attempt
  solution?: string
  sources?: Ref[]
}
export type Source = Ref & { filename: string; text: string; visualDescription: string; status: string; url: string; isPdf: boolean }

export type DesktopUpdate = {
  phase: 'idle' | 'checking' | 'current' | 'available' | 'downloading' | 'installing' | 'error'
  currentVersion: string
  availableVersion: string | null
  progress: number
  error: string | null
}

declare global {
  interface Window {
    tutorDesktop?: {
      remembered: (key: string) => string | null
      remember: (key: string, value: string | null) => void
      saveMarkdown: (filename: string, markdown: string) => Promise<boolean>
      updates: {
        status: () => Promise<DesktopUpdate | null>
        check: () => Promise<DesktopUpdate | null>
        install: () => Promise<DesktopUpdate | null>
        onStatus: (callback: (status: DesktopUpdate) => void) => () => void
      }
    }
  }
}

export class ApiError extends Error {
  constructor(public code: string, public status: number) {
    super(code)
  }
}

export async function api<T>(path: string, method = 'GET', body?: FormData | object, signal?: AbortSignal): Promise<T> {
  const json = body !== undefined && !(body instanceof FormData)
  const response = await fetch('/api/v1' + path, {
    method,
    signal,
    headers: json ? { 'Content-Type': 'application/json' } : undefined,
    body: json ? JSON.stringify(body) : body as FormData | undefined,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(payload?.error?.code ?? 'connection_error', response.status)
  }
  return response.json() as Promise<T>
}

export const uid = () => crypto.randomUUID()
export const pendingJob = (job: Job) => job.status === 'queued' || job.status === 'running'
export const coursePath = (id: string) => '/courses/' + id

export function remembered(key: string): string | null {
  if (window.tutorDesktop) return window.tutorDesktop.remembered(key)
  return localStorage.getItem('tutor.' + key)
}

export function remember(key: string, value: string | null): void {
  if (window.tutorDesktop) {
    window.tutorDesktop.remember(key, value)
    return
  }
  if (value === null) localStorage.removeItem('tutor.' + key)
  else localStorage.setItem('tutor.' + key, value)
}
