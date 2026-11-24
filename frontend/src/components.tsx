import { useEffect, useRef, type ReactNode } from 'react'
import katex from 'katex'
import { AlertCircle, BookOpen, Check, ClipboardList, ExternalLink, FileText, LoaderCircle, X } from 'lucide-react'
import type { Job, Locale, Ref, Source, Topic } from './api'
import { pendingJob } from './api'
import { explain, unitLabel, type Copy } from './copy'

export function Formula({ value, display = false }: { value: string; display?: boolean }) {
  try {
    const html = katex.renderToString(value, { throwOnError: true, strict: 'ignore', displayMode: display, trust: false })
    return <span className="formula" dangerouslySetInnerHTML={{ __html: html }} />
  } catch {
    return <span className="formula-fallback">{value}</span>
  }
}

export function MathText({ children }: { children: string }) {
  return <span className="math-text">{children.split(/(\$\$[^$]+\$\$|\$[^$\n]+\$|\\\([^\n]*?\\\)|\\\[[\s\S]*?\\\])/g).map((part, index) => {
    if (part.startsWith('$$') && part.endsWith('$$') && part.length > 4) {
      return <Formula key={index} value={part.slice(2, -2)} display />
    }
    if (part.startsWith('$') && part.endsWith('$') && part.length > 2) {
      return <Formula key={index} value={part.slice(1, -1)} />
    }
    if ((part.startsWith('\\(') && part.endsWith('\\)')) || (part.startsWith('\\[') && part.endsWith('\\]'))) {
      return <Formula key={index} value={part.slice(2, -2)} display={part[1] === '['} />
    }
    return <span key={index}>{part}</span>
  })}</span>
}

export function Modal({ title, children, close, closeLabel, className = '' }: {
  title: string; children: ReactNode; close?: () => void; closeLabel: string; className?: string
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])
  return (
    <dialog ref={ref} className={'modal ' + className} aria-label={title} onCancel={(event) => {
      event.preventDefault()
      close?.()
    }}>
      <div className="modal-header">
        <h2>{title}</h2>
        {close && <button className="icon-button" aria-label={closeLabel} onClick={close}><X size={20} /></button>}
      </div>
      {children}
    </dialog>
  )
}

export function Sources({ refs, locale, open, materialName }: {
  refs: Ref[]; locale: Locale; open: (ref: Ref) => void; materialName?: (ref: Ref) => string
}) {
  return <div className="source-links">{refs.map((ref) =>
    <button key={ref.materialId + ':' + ref.page} className="source-link" onClick={() => open(ref)}>
      <FileText size={14} /> {unitLabel(ref.page, locale, materialName?.(ref))}
    </button>,
  )}</div>
}

export function SourceModal({ source, locale, t, close }: { source: Source; locale: Locale; t: Copy; close: () => void }) {
  return <Modal title={t.sourcePreview} close={close} closeLabel={t.close} className="source-modal">
    <div className="source-meta"><FileText size={19} /> <strong>{source.filename}</strong><span>{unitLabel(source.page, locale, source.filename)}</span></div>
    <pre className="source-text">{source.text || t.unreadable}</pre>
    <div className="modal-footer">
      <a className="button primary" href={source.url} target={source.isPdf ? '_blank' : undefined}
        rel={source.isPdf ? 'noopener noreferrer' : undefined} download={!source.isPdf}>
        <ExternalLink size={17} /> {source.isPdf ? t.openPdf : t.downloadOriginal}
      </a>
    </div>
  </Modal>
}

export function Empty({ title, detail, icon = 'book', children }: {
  title: string; detail: string; icon?: 'book' | 'review'; children?: ReactNode
}) {
  return <div className="empty-state">
    <div className="empty-icon">{icon === 'review' ? <ClipboardList size={37} strokeWidth={1.5} /> : <BookOpen size={38} strokeWidth={1.5} />}</div>
    <h2>{title}</h2><p>{detail}</p>{children}
  </div>
}

export function Jobs({ jobs, locale, t, retry }: { jobs: Job[]; locale: Locale; t: Copy; retry: (job: Job) => void }) {
  return <div className="job-list">{jobs.map((job) => (
    <div className={'job ' + (job.status === 'failed' ? 'job-failed' : '')} key={job.jobId} role="status">
      {pendingJob(job) ? <LoaderCircle size={16} className="spin" /> : <AlertCircle size={16} />}
      <span>{job.error ? explain(job.error, locale) : job.kind === 'evaluate' ? t.grading : t[job.stage]}</span>
      {job.status === 'failed' && <button className="text-button" onClick={() => retry(job)}>{t.retry}</button>}
    </div>
  ))}</div>
}

export function TopicButton({ topic, current, t, level, select }: {
  topic: Topic; current: boolean; t: Copy; level: number; select: () => void
}) {
  const warning = topic.coverage === 'missing' || topic.status === 'review_needed' || topic.status === 'pending'
  const state = topic.coverage === 'missing' ? t.missing : topic.status && topic.status !== 'unassessed' ? t[topic.status] : null
  return <button
    className={'topic-button ' + (current ? 'current' : '')}
    style={{ paddingInlineStart: 10 + Math.min(level, 4) * 14 }}
    aria-current={current ? 'true' : undefined} onClick={select}
  >
    {topic.status === 'resolved' ? <Check size={17} /> : <BookOpen size={17} />}
    <span><MathText>{topic.title}</MathText></span>
    {state && <small className={'badge' + (warning ? ' warning' : '')}>{state}</small>}
  </button>
}
