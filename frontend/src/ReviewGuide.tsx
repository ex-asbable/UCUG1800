import { useEffect, useState } from 'react'
import { Download, FileText, LoaderCircle } from 'lucide-react'
import Markdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { api, ApiError, coursePath, pendingJob, type Job, type Locale, type Ref, type ReviewGuide as Guide } from './api'
import { Modal } from './components'
import { explain, unitLabel, type Copy } from './copy'

type GuideJob = Job & { result: Guide | null }

function escapedLabel(value: string) {
  return value.replace(/[\\`*_{}\[\]<>#|~$&]/g, '\\$&')
}

export function ReviewGuide({ courseId, outlineId, topicId, title, locale, t, materialName, openSource, close }: {
  courseId: string; outlineId: string; topicId: string; title: string; locale: Locale; t: Copy
  materialName: (ref: Ref) => string; openSource: (ref: Ref) => void; close: () => void
}) {
  const [job, setJob] = useState<GuideJob | null>(null)
  const [problem, setProblem] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'saved' | 'failed' | ''>('')
  const path = coursePath(courseId)
  const guide = job?.status === 'ready' ? job.result : null

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const fail = (error: unknown) => {
      if (!controller.signal.aborted) setProblem(error instanceof ApiError ? error.code : 'connection_error')
    }
    async function poll(id: string) {
      try {
        const current = await api<GuideJob>(path + '/jobs/' + id, 'GET', undefined, controller.signal)
        if (controller.signal.aborted) return
        setJob(current)
        if (pendingJob(current)) timer = setTimeout(() => void poll(id), 1000)
      } catch (error) { fail(error) }
    }
    api<{ jobId: string }>(path + '/topics/' + topicId + '/guide', 'POST', { outlineId }, controller.signal)
      .then(({ jobId }) => { if (!controller.signal.aborted) void poll(jobId) })
      .catch(fail)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [path, outlineId, topicId, attempt])

  async function retry() {
    setBusy(true)
    try {
      if (job?.status === 'failed') await api(path + '/jobs/' + job.jobId + '/retry', 'POST')
      setProblem('')
      setJob(null)
      setAttempt((value) => value + 1)
    } catch (error) {
      setProblem(error instanceof ApiError ? error.code : 'connection_error')
    } finally {
      setBusy(false)
    }
  }

  function citation(ref: Ref) {
    const name = materialName(ref)
    return `${name} · ${unitLabel(ref.page, locale, name)}`
  }

  async function save() {
    if (!guide) return
    const stem = title.replace(/[<>:"/\\|?*\p{Cc}]/gu, ' ').trim().slice(0, 70).replace(/[. ]+$/, '')
    const filename = stem ? `${stem}-review.md` : 'review.md'
    const citations = guide.sources.map((ref) => '- ' + escapedLabel(citation(ref))).join('\n')
    const markdown = `${guide.markdown}\n\n## ${t.sources}\n\n${citations}\n`
    setSaveStatus('')
    setBusy(true)
    try {
      if (window.tutorDesktop) {
        if (await window.tutorDesktop.saveMarkdown(filename, markdown)) setSaveStatus('saved')
      } else {
        const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        link.click()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
    } catch {
      setSaveStatus('failed')
    } finally {
      setBusy(false)
    }
  }

  const error = problem || job?.error
  return <Modal title={t.studyGuideTitle} close={close} closeLabel={t.close} className="guide-modal">
    {guide ? <>
      <div className="guide-actions">
        {saveStatus && <span role="status">{saveStatus === 'saved' ? t.markdownSaved : t.markdownSaveError}</span>}
        <button className="button primary" disabled={busy} onClick={() => void save()}>
          <Download size={17} />{t.saveMarkdown}
        </button>
      </div>
      <article className="guide-markdown">
        <Markdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} skipHtml
          components={{ a: ({ children }) => <span>{children}</span>, img: () => null }}>
          {guide.markdown}
        </Markdown>
      </article>
      <section className="guide-sources">
        <h3>{t.sources}</h3>
        {guide.sources.map((ref) => <button key={ref.materialId + ':' + ref.page}
          className="source-link" onClick={() => openSource(ref)}><FileText size={15} />{citation(ref)}</button>)}
      </section>
    </> : error ? <div className="warning-banner" role="alert">
      <span>{explain(error, locale)}</span>
      <button className="text-button" disabled={busy} onClick={() => void retry()}>{t.retry}</button>
    </div> : <div className="loading" role="status"><LoaderCircle className="spin" size={19} />{t.writingGuide}</div>}
  </Modal>
}
