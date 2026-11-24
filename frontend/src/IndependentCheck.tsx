import { useEffect, useState } from 'react'
import { CheckCircle2, CircleHelp, LoaderCircle } from 'lucide-react'
import { type Answer, type Check, type Job, type Locale, type Ref, remember, remembered } from './api'
import { explain, type Copy } from './copy'
import { Formula, Jobs, MathText, Modal, Sources } from './components'

type Draft = { answer: Answer; reason: string }

function restoreDraft(check: Check): Draft {
  try {
    const saved = remembered('check.' + check.id)
    if (saved) return JSON.parse(saved) as Draft
  } catch {
    remember('check.' + check.id, null)
  }
  return { answer: check.format === 'choice' ? '' : {}, reason: '' }
}

export function IndependentCheck({ check, jobs, locale, t, busy, error, setLanguage, close, leave, submit, openSource, materialName, retry }: {
  check: Check; jobs: Job[]; locale: Locale; t: Copy; busy: boolean; error: string
  setLanguage: (value: Locale) => void
  close: () => void; leave: () => void; submit: (answer: Answer, reason: string) => void
  openSource: (ref: Ref) => void; materialName: (ref: Ref) => string; retry: (job: Job) => void
}) {
  const [draft, setDraft] = useState(() => restoreDraft(check))
  useEffect(() => {
    remember('check.' + check.id, check.status === 'open' ? JSON.stringify(draft) : null)
  }, [check.id, check.status, draft])

  const editable = check.status === 'open'
  const answer = check.attempt?.answer ?? draft.answer
  const reason = check.attempt?.reason ?? draft.reason
  const result = check.attempt?.result
  const filled = typeof answer === 'string' ? !!answer : Object.values(answer).some((value) => value.trim())

  return <Modal
    title={t.check} close={editable ? leave : check.status === 'graded' ? close : undefined}
    closeLabel={editable ? t.leaveCheck : t.close} className="check-modal"
  >
    <label className="language-select check-language">
      <select aria-label={t.language} value={locale} disabled={busy} onChange={(event) => setLanguage(event.target.value as Locale)}>
        <option value="zh-Hans">简体中文</option><option value="en">English</option>
      </select>
    </label>
    {error && <p className="warning-banner" role="alert">{explain(error, locale)}</p>}
    <div className="check-prompt"><MathText>{check.prompt}</MathText></div>
    <form onSubmit={(event) => {
      event.preventDefault()
      if (filled && editable) submit(typeof answer === 'string' ? answer :
        Object.fromEntries(check.fields.map((field) => [field.id, answer[field.id] ?? ''])), reason)
    }}>
      <fieldset disabled={!editable || busy}>
        <legend className="visually-hidden">{t.answer}</legend>
        {check.format === 'choice' ? check.options.map((option) => (
          <label className={'answer-choice ' + (answer === option.id ? 'selected' : '')} key={option.id}>
            <input type="radio" name={'choice-' + check.id} checked={answer === option.id} onChange={() => setDraft({ ...draft, answer: option.id })} />
            <MathText>{option.text}</MathText>
          </label>
        )) : check.fields.map((field) => {
          const text = typeof answer === 'string' ? '' : answer[field.id] ?? ''
          return <label className="answer-field" key={field.id}>
            <MathText>{field.label || t.answer}</MathText>
            {check.format === 'tex' ? <>
              <input
                className="tex-input" value={text} maxLength={160} autoComplete="off" spellCheck={false}
                onChange={(event) => setDraft({ ...draft, answer: { ...(typeof answer === 'string' ? {} : answer), [field.id]: event.target.value } })}
              />
              {!!text.trim() && <div className="formula-preview" aria-label={t.texPreview}><Formula value={text} /></div>}
            </> : <textarea
              value={text} maxLength={2500} rows={2}
              onChange={(event) => setDraft({ ...draft, answer: { ...(typeof answer === 'string' ? {} : answer), [field.id]: event.target.value } })}
            />}
          </label>
        })}
        {check.requiresReason && <label className="answer-field">{t.reason}
          <textarea maxLength={4000} rows={2} value={reason} onChange={(event) => setDraft({ ...draft, reason: event.target.value })} />
        </label>}
      </fieldset>
      {editable && <div className="modal-footer">
        <button type="button" className="button secondary" onClick={leave} disabled={busy}>{t.leaveCheck}</button>
        <button type="submit" className="button primary" disabled={!filled || busy}>{t.submit}</button>
      </div>}
    </form>
    {check.status === 'submitted' && (jobs.length ? <Jobs jobs={jobs} locale={locale} t={t} retry={retry} /> :
      <div className="job" role="status"><LoaderCircle size={17} className="spin" /> {t.grading}</div>)}
    {result && <div className={'check-result ' + result.correctness}>
      <strong>{result.correctness === 'correct' ? <CheckCircle2 size={19} /> : <CircleHelp size={19} />} {t[result.correctness]}</strong>
      {result.gapStatus && <span className="badge">{t[result.gapStatus]}</span>}
      <p><MathText>{result.feedback || explain(result.feedbackCode ?? 'insufficient_evidence', locale)}</MathText></p>
      {result.evidence && <blockquote>{result.evidence}</blockquote>}
      {check.solution && <details open><summary>{t.solution}</summary><p><MathText>{check.solution}</MathText></p></details>}
      {!!check.sources?.length && <Sources refs={check.sources} locale={locale} open={openSource} materialName={materialName} />}
    </div>}
  </Modal>
}
