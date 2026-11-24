import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  AlertCircle, BookOpen, CheckCircle2, ChevronRight, ClipboardList, FileText, FolderOpen, GraduationCap,
  History, Languages, LoaderCircle, MessageSquarePlus, Plus, Send, Settings2, Upload, X,
} from 'lucide-react'
import {
  api, ApiError, coursePath, pendingJob, remember, remembered, uid,
  type Answer, type Catalog, type Check, type Course, type Format, type Gap, type ImportIssue, type Job, type Locale,
  type Ref, type ReviewGroup, type Runtime, type Session, type SessionItem, type Source, type Topic,
} from './api'
import { copy, explain, unitLabel } from './copy'
import { Empty, Jobs, MathText, Modal, SourceModal, Sources, TopicButton } from './components'
import { IndependentCheck } from './IndependentCheck'
import { ModelSettings } from './ModelSettings'
import { ReviewGuide } from './ReviewGuide'

type ViewData = {
  locale: Locale
  courseId: string
  topics: Topic[]
  sessions: SessionItem[]
  review: ReviewGroup[]
}
type Task = { jobId: string }
type InputModal = 'course' | 'question' | null
const mib = 1024 * 1024

function code(error: unknown): string {
  return error instanceof ApiError ? error.code : 'connection_error'
}

function topicOrder(topics: Topic[]) {
  const children = new Map<string | null, Topic[]>()
  for (const topic of topics) children.set(topic.parentId, [...(children.get(topic.parentId) ?? []), topic])
  const branch = (parent: string | null, level: number): { topic: Topic; level: number }[] =>
    (children.get(parent) ?? []).flatMap((topic) => [{ topic, level }, ...branch(topic.id, level + 1)])
  return branch(null, 0)
}

export function App() {
  const [locale, setLocale] = useState<Locale>('zh-Hans')
  const [loadingLanguage, setLoadingLanguage] = useState(false)
  const [courses, setCourses] = useState<Course[] | null>(null)
  const [runtime, setRuntime] = useState<Runtime | null>(null)
  const [showRuntimeSettings, setShowRuntimeSettings] = useState(false)
  const [courseId, setCourseId] = useState('')
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [data, setData] = useState<ViewData | null>(null)
  const [sessionId, setSessionId] = useState('')
  const [session, setSession] = useState<Session | null>(null)
  const [topicId, setTopicId] = useState('')
  const [explicitCheckId, setExplicitCheckId] = useState('')
  const [check, setCheck] = useState<Check | null>(null)
  const [source, setSource] = useState<Source | null>(null)
  const [guide, setGuide] = useState<{ topic: Topic; outlineId: string } | null>(null)
  const [folderIssues, setFolderIssues] = useState<{ courseId: string; files: ImportIssue[] } | null>(null)
  const [view, setView] = useState<'tutor' | 'review'>('tutor')
  const [version, setVersion] = useState(0)
  const [initialVersion, setInitialVersion] = useState(0)
  const [modal, setModal] = useState<InputModal>(null)
  const [modalText, setModalText] = useState('')
  const [message, setMessage] = useState('')
  const [format, setFormat] = useState<Format>('text')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [viewError, setViewError] = useState('')
  const [checkError, setCheckError] = useState('')
  const file = useRef<HTMLInputElement>(null)
  const folder = useRef<HTMLInputElement>(null)
  const replacement = useRef<string | null>(null)
  const busyNow = useRef(false)
  const requests = useRef(new Map<string, string>())
  const sessionEnd = useRef<HTMLDivElement>(null)
  const catalogSignature = useRef<{ courseId: string; value: string } | null>(null)
  const t = copy(locale)

  const currentCatalog = catalog?.course.id === courseId ? catalog : null
  const currentData = data?.courseId === courseId && data.locale === locale ? data : null
  const currentSession = session?.id === sessionId && session.locale === locale ? session : null
  const locked = currentSession?.check?.status === 'open' || currentSession?.check?.status === 'submitted'
  const openCheckId = locked ? currentSession!.check!.id : explicitCheckId
  const activeCheck = check?.id === openCheckId && check.locale === locale ? check : null
  const topics = currentData?.topics ?? []
  const selectedTopic = currentSession?.topic ?? topics.find((topic) => topic.id === topicId)
  const activeGaps = currentSession?.gaps.filter((gap) => ['pending', 'review_needed'].includes(gap.status)) ?? []
  const sessionBusy = currentSession?.jobs.some(pendingJob) ?? false
  const reviewCount = currentData?.review.reduce((sum, item) => sum + item.count, 0) ?? 0
  const hasOutline = !!currentCatalog?.course.outlineId

  function reload() { setVersion((value) => value + 1) }

  async function once<T>(key: string, run: (requestId: string) => Promise<T>) {
    const requestId = requests.current.get(key) ?? uid()
    requests.current.set(key, requestId)
    const value = await run(requestId)
    requests.current.delete(key)
    return value
  }

  function selectSession(id: string, targetCourse = courseId) {
    setSessionId(id)
    setExplicitCheckId('')
    setCheck(null)
    setMessage('')
    if (targetCourse) remember('session.' + targetCourse, id || null)
  }

  function selectCourse(id: string) {
    setCourseId(id)
    setTopicId('')
    setView('tutor')
    selectSession(id ? remembered('session.' + id) ?? '' : '', id)
    remember('course', id || null)
  }

  useEffect(() => {
    let live = true
    Promise.all([api<{ locale: Locale }>('/preferences'), api<{ courses: Course[] }>('/courses')]).then(([pref, list]) => {
      if (!live) return
      setLocale(pref.locale)
      setCourses(list.courses)
      const initial = list.courses.find((course) => course.id === remembered('course')) ?? list.courses[0]
      selectCourse(initial?.id ?? '')
    }).catch((problem) => { if (live) setError(code(problem)) })
    api<Runtime>('/runtime/status').then((status) => { if (live) setRuntime(status) }).catch(() => {})
    return () => { live = false }
  }, [initialVersion])

  useEffect(() => { document.documentElement.lang = locale }, [locale])

  useEffect(() => {
    if (!courseId) return
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const value = await api<Catalog>(coursePath(courseId) + '/materials')
        if (!live) return
        const signature = JSON.stringify([value.course.outlineId, value.jobs.map((job) => [job.jobId, job.status])])
        const previous = catalogSignature.current
        catalogSignature.current = { courseId, value: signature }
        setCatalog(value)
        if (previous?.courseId === courseId && signature !== previous.value) {
          reload()
        } else if (value.jobs.some(pendingJob)) {
          timer = setTimeout(poll, 1200)
        }
      } catch (problem) {
        if (!live) return
        if (problem instanceof ApiError && problem.status === 404) {
          remember('session.' + courseId, null)
          let remaining = (courses ?? []).filter((course) => course.id !== courseId)
          try {
            const list = await api<{ courses: Course[] }>('/courses')
            remaining = list.courses.filter((course) => course.id !== courseId)
          } catch (refreshError) {
            if (live) setError(code(refreshError))
          }
          if (live) {
            setCourses(remaining)
            selectCourse(remaining[0]?.id ?? '')
            setViewError('')
          }
          return
        }
        setError(code(problem))
        timer = setTimeout(poll, 4000)
      }
    }
    void poll()
    return () => { live = false; clearTimeout(timer) }
  }, [courseId, version])

  useEffect(() => {
    function refreshOnReturn() { if (document.visibilityState === 'visible') reload() }
    document.addEventListener('visibilitychange', refreshOnReturn)
    return () => document.removeEventListener('visibilitychange', refreshOnReturn)
  }, [])

  useEffect(() => {
    if (!courseId || loadingLanguage) return
    let live = true
    const path = coursePath(courseId)
    setViewError('')
    Promise.all([
      api<{ locale: Locale; topics: Topic[] }>(path + '/topics'),
      api<{ locale: Locale; sessions: SessionItem[] }>(path + '/sessions'),
      api<{ locale: Locale; topics: ReviewGroup[] }>(path + '/review'),
    ]).then(([outline, list, review]) => {
      if (live && [outline.locale, list.locale, review.locale].every((value) => value === locale)) {
        setData({ locale, courseId, topics: outline.topics, sessions: list.sessions, review: review.topics })
      }
    }).catch((problem) => {
      if (live && !(problem instanceof ApiError && problem.status === 404)) {
        setViewError(code(problem))
      }
    })
    return () => { live = false }
  }, [courseId, locale, loadingLanguage, version])

  useEffect(() => {
    if (!sessionId || loadingLanguage) return
    let live = true
    api<Session>('/sessions/' + sessionId).then((value) => {
      if (live && value.locale === locale) {
        setSession(value)
        if (value.check?.status === 'open' || value.check?.status === 'submitted') setExplicitCheckId(value.check.id)
      }
    }).catch((problem) => {
      if (!live) return
      if (problem instanceof ApiError && problem.status === 404) {
        setSession(null)
        selectSession('')
      } else {
        setViewError(code(problem))
      }
    })
    return () => { live = false }
  }, [sessionId, locale, loadingLanguage, version])

  useEffect(() => {
    if (!openCheckId || loadingLanguage) return
    let live = true
    setCheckError('')
    api<Check>('/checks/' + openCheckId).then((value) => {
      if (live && value.locale === locale) setCheck(value)
    }).catch((problem) => { if (live) setCheckError(code(problem)) })
    return () => { live = false }
  }, [openCheckId, locale, loadingLanguage, version])

  useEffect(() => {
    if (currentSession?.messages.length) sessionEnd.current?.scrollIntoView({ block: 'nearest' })
  }, [currentSession?.messages.length, sessionId])

  async function act(action: () => Promise<void>) {
    if (busyNow.current) return
    busyNow.current = true
    setBusy(true)
    setError('')
    try { await action() }
    catch (problem) { setError(code(problem)) }
    finally { setBusy(false); busyNow.current = false }
  }

  async function switchLanguage(next: Locale) {
    if (next === locale || loadingLanguage) return
    const previous = locale
    setLocale(next)
    setLoadingLanguage(true)
    try { await api('/preferences', 'PATCH', { locale: next }) }
    catch (problem) { setError(code(problem)); setLocale(previous) }
    finally { setLoadingLanguage(false) }
  }

  function openInput(target: InputModal) {
    setModalText('')
    setModal(target)
  }

  function submitModal(event: FormEvent) {
    event.preventDefault()
    if (!modalText.trim()) return
    void act(async () => {
      if (modal === 'course') {
        const course = await api<Course>('/courses', 'POST', { name: modalText.trim() })
        setCourses((list) => [course, ...(list ?? [])])
        selectCourse(course.id)
      } else {
        await startSession(null, modalText.trim())
      }
      setModal(null)
    })
  }

  async function startSession(topic: string | null, question: string | null) {
    const result = await api<Task & { sessionId: string }>(coursePath(courseId) + '/sessions', 'POST', {
      topicId: topic, question, requestId: uid(),
    })
    setView('tutor')
    selectSession(result.sessionId)
    reload()
  }

  function openTopic(topic: Topic) {
    setTopicId(topic.id)
    setView('tutor')
    const existing = currentData?.sessions.find((item) => item.topicId === topic.id)
    selectSession(topic.coverage === 'missing' ? '' : existing?.id ?? '')
  }

  function selectFile(replaces: string | null = null) {
    replacement.current = replaces
    file.current?.click()
  }

  function upload(files: FileList | null) {
    if (!files?.length) return
    const list = Array.from(files)
    const replaces = replacement.current
    replacement.current = null
    void act(async () => {
      for (const item of replaces ? list.slice(0, 1) : list) {
        const key = JSON.stringify([courseId, replaces, item.name, item.size, item.lastModified])
        await once(key, (requestId) => {
          const body = new FormData()
          body.append('file', item)
          body.append('requestId', requestId)
          if (replaces) body.append('replacesId', replaces)
          return api(coursePath(courseId) + '/materials', 'POST', body)
        })
      }
      reload()
    })
  }

  function uploadFolder(files: FileList | null) {
    if (!files?.length) return
    const list = Array.from(files).sort((a, b) => a.webkitRelativePath.localeCompare(b.webkitRelativePath))
    void act(async () => {
      const problems: ImportIssue[] = []
      const body = new FormData()
      const selected = list.filter((item) => {
        if (item.size <= 30 * mib) return true
        problems.push({ filename: item.webkitRelativePath || item.name, code: 'file_too_large' })
        return false
      })
      setFolderIssues({ courseId, files: problems })
      if (!selected.length) return
      if (selected.length > 1000 || selected.reduce((size, item) => size + item.size, 0) > 512 * mib) {
        throw new ApiError('folder_too_large', 413)
      }
      const key = JSON.stringify(['folder', courseId, selected.map((item) =>
        [item.webkitRelativePath || item.name, item.size, item.lastModified])])
      for (const item of selected) body.append('files', item, item.webkitRelativePath || item.name)
      const result = await once(key, (requestId) => {
        body.set('requestId', requestId)
        return api<{ jobId: string | null; issues: ImportIssue[] }>(coursePath(courseId) + '/materials/folder', 'POST', body)
      })
      setFolderIssues({ courseId, files: [...problems, ...result.issues] })
      reload()
    })
  }

  function sendMessage(event: FormEvent) {
    event.preventDefault()
    const text = message.trim()
    if (!text || !sessionId || sessionBusy) return
    void act(async () => {
      await once(JSON.stringify([sessionId, text]), (requestId) =>
        api('/sessions/' + sessionId + '/messages', 'POST', { text, requestId }))
      setMessage('')
      reload()
    })
  }

  function requestCheck(gap?: Gap) {
    void act(async () => {
      const target = gap?.sessionId ?? sessionId
      await api('/sessions/' + target + '/checks', 'POST', {
        format, gapId: gap?.id ?? null,
        purpose: gap ? gap.status === 'review_needed' ? 'review' : 'confirm' : 'practice', requestId: uid(),
      })
      if (target !== sessionId) selectSession(target)
      setExplicitCheckId('')
      setView('tutor')
      reload()
    })
  }

  function retry(job: Job) {
    void act(async () => {
      await api(coursePath(courseId) + '/jobs/' + job.jobId + '/retry', 'POST')
      reload()
    })
  }

  function openSource(ref: Ref) {
    void act(async () => {
      setSource(await api<Source>(coursePath(courseId) + '/materials/' + ref.materialId + '/units/' + ref.page))
    })
  }

  function showResult(id: string) { setExplicitCheckId(id) }

  function submitAnswer(checkId: string, answer: Answer, reason: string) {
    void act(async () => {
      const key = 'submit.' + checkId
      const requestId = remembered(key) ?? uid()
      remember(key, requestId)
      await api('/checks/' + checkId + '/attempts', 'POST', { answer, reason, requestId })
      remember(key, null)
      setExplicitCheckId(checkId)
      reload()
    })
  }

  function leaveCheck(checkId: string) {
    void act(async () => {
      await api('/checks/' + checkId + '/leave', 'POST')
      remember('check.' + checkId, null)
      setExplicitCheckId('')
      setCheck(null)
      setSession(null)
      reload()
    })
  }

  const importJobs = currentCatalog?.jobs.filter((job) => job.kind === 'import' || job.kind === 'folder') ?? []
  const currentFolderIssues = folderIssues?.courseId === courseId ? folderIssues.files : []
  const materialName = (ref: Ref) => currentCatalog?.materials.find((item) => item.id === ref.materialId)?.filename ?? ''
  const references = (currentSession?.messages.slice().reverse().find((item) => item.sources.length)?.sources ?? selectedTopic?.sources ?? [])
    .filter((ref, index, all) => all.findIndex((item) => item.materialId === ref.materialId && item.page === ref.page) === index)
  const sessionTitle = selectedTopic?.title ?? (currentSession ? t.newQuestion : '')

  return <div className="shell">
    <header className="topbar">
      <div className="brand"><span className="brand-icon"><GraduationCap size={25} /></span><span>AI Tutor</span></div>
      <div className="top-actions">
        <button className={'runtime ' + (runtime?.ready ? 'runtime-ready' : 'runtime-error')}
          aria-label={t.runtimeSettings} title={runtime?.error ? explain(runtime.error, locale) : t.runtimeSettings}
          onClick={() => runtime ? setShowRuntimeSettings(true) : void act(async () => {
            setRuntime(await api<Runtime>('/runtime/status'))
            setShowRuntimeSettings(true)
          })}>
          <Settings2 size={16} /><span>{runtime?.provider === 'api' ? t.modelApi : runtime ? 'Codex CLI' : t.runtime}</span>
          {runtime && <i />}
        </button>
        <label className="language-select"><Languages size={17} aria-hidden="true" />
          <select aria-label={t.language} value={locale} disabled={loadingLanguage}
            onChange={(event) => void switchLanguage(event.target.value as Locale)}>
            <option value="zh-Hans">简体中文</option><option value="en">English</option>
          </select>
        </label>
        {courseId && <button className="button primary header-upload" onClick={() => selectFile()} disabled={busy}>
          <Upload size={17} />{t.upload}
        </button>}
        {courseId && <button className="button secondary header-upload" onClick={() => folder.current?.click()} disabled={busy}>
          <FolderOpen size={17} />{t.importFolder}
        </button>}
      </div>
    </header>
    <input ref={file} type="file" accept="application/pdf,.pdf" multiple hidden aria-label={t.filePrompt}
      onChange={(event) => { upload(event.target.files); event.target.value = '' }} />
    <input ref={folder} type="file" hidden aria-label={t.importFolder} {...{ webkitdirectory: '' }}
      onChange={(event) => { uploadFolder(event.target.files); event.target.value = '' }} />

    <div className={'app-body ' + (!courseId ? 'onboarding' : '')}>
      <aside className="sidebar" aria-label={t.courses}>
        <div className="side-section course-select">
          <h2>{t.courses}</h2>
          <div className="course-controls">
            <select aria-label={t.courses} value={courseId} onChange={(event) => selectCourse(event.target.value)}>
              {!courses?.length && <option value="">{t.noCourses}</option>}
              {courses?.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}
            </select>
            <button className="icon-button add-course" aria-label={t.newCourse} title={t.newCourse} onClick={() => openInput('course')}><Plus size={21} /></button>
          </div>
        </div>
        {courseId && <>
          <section className="side-section">
            <div className="side-heading"><h2>{t.materials}</h2>
              <button className="icon-button" aria-label={t.upload} onClick={() => selectFile()}><Plus size={17} /></button>
            </div>
            {!currentCatalog?.materials.length && <p className="side-empty">{t.noMaterialsSide}</p>}
            {currentCatalog?.materials.filter((item) => item.status !== 'superseded').map((item) => (
              <div className="material" key={item.id}>
                <div className="material-row"><span className="file-icon"><FileText size={18} /></span>
                  <div><strong title={item.filename}>{item.filename}</strong>
                    <small className={'material-status ' + item.status}>
                      {t[item.status]}{item.pageCount ? ' · ' + item.pageCount + ' ' +
                        (item.filename.toLowerCase().endsWith('.pdf') ? t.pages :
                          item.filename.toLowerCase().endsWith('.pptx') ? t.slide : t.section) : ''}
                    </small>
                  </div>
                </div>
                {item.issue && <p className="material-issue">{explain(item.issue, locale)}</p>}
                {item.active && item.filename.toLowerCase().endsWith('.pdf') &&
                  <button className="text-button small" onClick={() => selectFile(item.id)}>{t.replace}</button>}
                {item.status === 'attached' || !item.filename.toLowerCase().endsWith('.pdf') ?
                  <a className="text-button small" href={'/api/v1' + coursePath(courseId) + '/materials/' + item.id + '/original'}
                    download>{t.downloadOriginal}</a> : null}
                {!!item.unreadablePages.length && <details className="unreadable">
                  <summary>{t.unreadable}</summary>
                  <Sources locale={locale} refs={item.unreadablePages.map((page) => ({ materialId: item.id, page }))}
                    open={openSource} materialName={materialName} />
                </details>}
              </div>
            ))}
          </section>
          <section className="side-section outline">
            <div className="side-heading"><h2>{t.outline}</h2></div>
            <nav aria-label={t.outline}>{topicOrder(topics).map(({ topic, level }) => <TopicButton
              key={topic.id} topic={topic} level={level} current={view === 'tutor' && selectedTopic?.id === topic.id}
              t={t} select={() => openTopic(topic)}
            />)}</nav>
          </section>
          <section className="side-section">
            <button aria-current={view === 'review' ? 'page' : undefined} className={'side-nav ' + (view === 'review' ? 'current' : '')}
              onClick={() => setView('review')}><ClipboardList size={19} /><span>{t.review}</span>{reviewCount > 0 && <b>{reviewCount}</b>}</button>
            {!!currentData?.sessions.length && <details className="session-list">
              <summary><History size={18} /> {t.sessions}</summary>
              {currentData.sessions.map((item) => <button key={item.id} className={item.id === sessionId ? 'current' : ''}
                onClick={() => { selectSession(item.id); setTopicId(item.topicId ?? ''); setView('tutor') }}>
                {item.title ?? t.newQuestion}
              </button>)}
            </details>}
          </section>
        </>}
      </aside>

      <main className="main">
        {error && <div className="warning-banner" role="alert">
          <AlertCircle size={18} /> <span>{explain(error, locale)}</span>
          {!courses && <button className="text-button" onClick={() => { setError(''); setInitialVersion((value) => value + 1) }}>{t.retry}</button>}
          <button className="icon-button" aria-label={t.dismiss} onClick={() => setError('')}><X size={17} /></button>
        </div>}
        {!!currentFolderIssues.length && <details className="warning-banner import-issues" open>
          <summary>{t.importIssues} ({currentFolderIssues.length})</summary>
          <ul>{currentFolderIssues.map((issue, index) =>
            <li key={index}>{issue.filename} · {explain(issue.code, locale)}</li>)}</ul>
          <button className="text-button" onClick={() => setFolderIssues(null)}>{t.dismiss}</button>
        </details>}
        {!!runtime?.error && <div className="warning-banner" role="status"><AlertCircle size={18} /><span>{explain(runtime.error, locale)}</span>
          <button className="text-button" onClick={() => setShowRuntimeSettings(true)}>{t.runtimeSettings}</button>
        </div>}
        {courseId && viewError && <div className="warning-banner" role="alert"><AlertCircle size={18} />
          <span>{explain(viewError, locale)}</span><button className="text-button" onClick={reload}>{t.retry}</button>
        </div>}
        {!courses ? <div className="loading" role="status"><LoaderCircle className="spin" size={20} />{t.loadingCourse}</div>
          : !courseId ? <Empty title={t.noCourses} detail={t.noCoursesDetail}>
            <button className="button primary" onClick={() => openInput('course')}><Plus size={18} />{t.create}</button>
          </Empty>
          : <>
            <div className="workspace-header">
              <div>
                <div className="breadcrumb"><BookOpen size={14} /><span>{currentCatalog?.course.name ?? courses.find((item) => item.id === courseId)?.name}</span>
                  {(sessionTitle || view === 'review') && <><ChevronRight size={14} /><span>{view === 'review' ? t.review : t.tutor}</span></>}
                </div>
                <h1>{view === 'review' ? t.review : sessionTitle || currentCatalog?.course.name || t.tutor}</h1>
              </div>
              {hasOutline && <button className="button secondary" onClick={() => openInput('question')}>
                <MessageSquarePlus size={17} />{t.newQuestion}
              </button>}
            </div>
            {!!importJobs.length && <Jobs jobs={importJobs} t={t} locale={locale} retry={retry} />}
            {!currentCatalog || (hasOutline && (!currentData || loadingLanguage)) ? (
              <div className="loading" role="status"><LoaderCircle className="spin" size={20} />{loadingLanguage || hasOutline ? t.languageLoading : t.loading}</div>
            ) : view === 'review' ? (
              <div className="review-area">
                {!currentData?.review.length ? <Empty title={t.noReview} detail={t.noReviewDetail} icon="review" /> :
                  currentData.review.map((group) => <section className="panel review-group" key={group.topic.id}>
                    <div className="panel-heading"><ClipboardList size={20} /><h2>{group.topic.title}</h2><span className="badge warning">{group.count} · {t.review_needed}</span></div>
                    {group.gaps.map((gap) => <div className="review-gap" key={gap.id}>
                      <p className="gap-description"><MathText>{gap.description}</MathText></p>
                      <blockquote>{gap.evidence || gap.trigger}</blockquote>
                      <div className="gap-actions">
                        <button className="button primary" onClick={() => requestCheck(gap)} disabled={busy}>{t.reviewStart}</button>
                        {gap.checkId && <button className="button secondary" onClick={() => showResult(gap.checkId!)}>{t.viewResult}</button>}
                      </div>
                    </div>)}
                  </section>)}
              </div>
            ) : !hasOutline ? (
              currentCatalog.materials.length && importJobs.some(pendingJob)
                ? <Empty title={t.noTopics} detail={t.noTopicsDetail} />
                : <Empty title={t.noMaterials} detail={t.noMaterialsDetail}>
                  <div className="topic-actions">
                    <button className="button primary" onClick={() => selectFile()} disabled={busy}><Upload size={17} />{t.upload}</button>
                    <button className="button secondary" onClick={() => folder.current?.click()} disabled={busy}><FolderOpen size={17} />{t.importFolder}</button>
                  </div>
                </Empty>
            ) : !selectedTopic && !sessionId ? (
              <Empty title={t.chooseTopic} detail={t.chooseTopicDetail}><button className="button secondary" onClick={() => openInput('question')}>
                <MessageSquarePlus size={17} />{t.newQuestion}</button></Empty>
            ) : <div className="work-grid">
              <div className="tutor-pane">
                {selectedTopic && <section className="topic-overview">
                  {selectedTopic.coverage === 'missing' ? <>
                    <span className="badge warning">{t.missing}</span><p>{t.missingDetail}</p>
                    <button className="button primary" onClick={() => selectFile()}><Upload size={17} />{t.add}</button>
                  </> : <>
                    <span className="overview-label"><BookOpen size={17} />{selectedTopic.coverage === 'prerequisite' ? t.prerequisite : t.basedOn}</span>
                    <p><MathText>{selectedTopic.explanation}</MathText></p>
                    <div className="topic-actions">
                      {!sessionId && <button className="button primary" disabled={busy}
                        onClick={() => void act(() => startSession(selectedTopic.id, null))}>{t.startTutoring}</button>}
                      {currentSession && currentSession.outlineId !== currentCatalog.course.outlineId &&
                        topics.some((topic) => topic.id === selectedTopic.id && topic.coverage !== 'missing') &&
                        <button className="button secondary" disabled={busy}
                          onClick={() => void act(() => startSession(selectedTopic.id, null))}>{t.updatedTutoring}</button>}
                      <button className="button secondary" disabled={busy} onClick={() => setGuide({
                        topic: selectedTopic, outlineId: (currentSession?.outlineId ?? currentCatalog.course.outlineId)!,
                      })}><BookOpen size={17} />{t.studyGuide}</button>
                    </div>
                  </>}
                </section>}
                {sessionId && <section className="panel conversation">
                  {currentSession ? <>
                    <div className="messages" aria-live="polite">
                      {!currentSession.messages.length && !locked && !currentSession.jobs.length && <p className="muted">{t.emptyConversation}</p>}
                      {currentSession.messages.map((item) => <article className={'message ' + item.role} key={item.id}>
                        <div className="message-avatar">{item.role === 'tutor' ? <GraduationCap size={19} /> : t.me.slice(0, 1)}</div>
                        <div className="message-content"><strong>{item.role === 'tutor' ? t.tutor : t.me}</strong>
                          <div className="bubble"><MathText>{item.text}</MathText></div>
                          {!!item.sources.length && <Sources refs={item.sources} locale={locale} open={openSource} materialName={materialName} />}
                        </div>
                      </article>)}
                      <div ref={sessionEnd} />
                    </div>
                    {!locked && <><Jobs jobs={currentSession.jobs} t={t} locale={locale} retry={retry} />
                      <form className="composer" onSubmit={sendMessage}>
                        <textarea value={message} aria-label={t.reasonPlaceholder} maxLength={6000} rows={2}
                          placeholder={t.reasonPlaceholder} onChange={(event) => setMessage(event.target.value)} />
                        <button className="button primary" disabled={busy || sessionBusy || !message.trim()} type="submit">
                          <Send size={17} />{t.send}
                        </button>
                      </form></>}
                  </> : <div className="loading"><LoaderCircle className="spin" size={18} />{t.loading}</div>}
                </section>}
              </div>
              <aside className="study-tools">
                <section className="panel source-panel">
                  <div className="panel-heading"><FileText size={21} /><h2>{t.sources}</h2></div>
                  {references.length ? references.map((ref) => <button className="citation" key={ref.materialId + ':' + ref.page} onClick={() => openSource(ref)}>
                    <span className="file-icon"><FileText size={17} /></span><span><strong>{materialName(ref) || t.downloadOriginal}</strong>
                      <small>{unitLabel(ref.page, locale, materialName(ref))}</small></span><ChevronRight size={17} />
                  </button>) : <p className="muted">{t.noSource}</p>}
                </section>
                {sessionId && !locked && <section className="panel practice-panel">
                  <div className="panel-heading"><CheckCircle2 size={21} /><h2>{t.check}</h2></div>
                  <p className="muted">{t.checkIntro}</p>
                  <label className="field-label">{t.chooseFormat}<select value={format} onChange={(event) => setFormat(event.target.value as Format)}>
                    <option value="choice">{t.choice}</option><option value="text">{t.text}</option><option value="tex">{t.tex}</option>
                  </select></label>
                  {activeGaps.map((gap) => <div className="gap-card" key={gap.id}>
                    <span className="badge warning">{t[gap.status]}</span>
                    <p><MathText>{gap.description}</MathText></p>
                    {gap.reason && <small>{explain(gap.reason, locale)}</small>}
                    <button className="button secondary" disabled={busy || sessionBusy} onClick={() => requestCheck(gap)}>
                      {gap.status === 'review_needed' ? t.reviewStart : t.confirm}
                    </button>
                  </div>)}
                  {!activeGaps.length && <button className="button secondary" disabled={busy || sessionBusy || !currentSession?.topicId}
                    onClick={() => requestCheck()}>{t.checkStart}</button>}
                  {currentSession?.check?.status === 'graded' && <button className="text-button" onClick={() => showResult(currentSession.check!.id)}>{t.viewResult}</button>}
                </section>}
              </aside>
            </div>}
          </>}
      </main>
    </div>

    {modal && <Modal title={modal === 'course' ? t.newCourse : t.ask} close={() => setModal(null)} closeLabel={t.close}>
      <form onSubmit={submitModal}>
        {modal === 'course' ? <label className="field-label">{t.courseName}<input
          autoFocus value={modalText} placeholder={t.coursePlaceholder} maxLength={120} onChange={(event) => setModalText(event.target.value)}
        /></label> : <label className="field-label">{t.newQuestion}<textarea
          autoFocus value={modalText} placeholder={t.askPlaceholder} maxLength={6000} rows={4} onChange={(event) => setModalText(event.target.value)}
        /></label>}
        {error && <p className="warning-banner" role="alert">{explain(error, locale)}</p>}
        <div className="modal-footer"><button className="button secondary" type="button" onClick={() => setModal(null)}>{t.cancel}</button>
          <button className="button primary" disabled={busy || !modalText.trim()}>{modal === 'course' ? t.create : t.send}</button></div>
      </form>
    </Modal>}
    {openCheckId && (activeCheck ? <IndependentCheck
      key={activeCheck.id} check={activeCheck} jobs={currentSession?.jobs.filter((job) => job.kind === 'evaluate') ?? []}
      locale={locale} t={t} busy={busy} error={error} setLanguage={(value) => void switchLanguage(value)}
      close={() => setExplicitCheckId('')} leave={() => leaveCheck(activeCheck.id)}
      submit={(answer, reason) => submitAnswer(activeCheck.id, answer, reason)} openSource={openSource}
      materialName={materialName} retry={retry}
    /> : <Modal title={t.check} close={!locked ? () => setExplicitCheckId('') : undefined} closeLabel={t.close}>
      {checkError ? <div className="warning-banner"><span>{explain(checkError, locale)}</span>
        <button className="text-button" onClick={reload}>{t.retry}</button>
      </div> : <div className="loading"><LoaderCircle className="spin" size={18} />{t.loading}</div>}
    </Modal>)}
    {showRuntimeSettings && runtime && <ModelSettings runtime={runtime} locale={locale} t={t}
      close={() => setShowRuntimeSettings(false)} saved={(status) => {
        setRuntime(status)
        setShowRuntimeSettings(false)
        setError('')
        reload()
      }}
    />}
    {guide && <ReviewGuide key={courseId + guide.outlineId + guide.topic.id + locale}
      courseId={courseId} outlineId={guide.outlineId} topicId={guide.topic.id} title={guide.topic.title}
      locale={locale} t={t} materialName={materialName} openSource={openSource} close={() => setGuide(null)} />}
    {source && <SourceModal source={source} locale={locale} t={t} close={() => setSource(null)} />}
  </div>
}
