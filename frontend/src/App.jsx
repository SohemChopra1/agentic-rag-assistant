import { useEffect, useReducer, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'

import { streamAsk } from './api.js'
import './App.css'

const EXAMPLES = [
  'How much protein should I eat if I weigh 80 kg?',
  'How much physical activity do adults need each week?',
  'How many hours of sleep should adults get?',
]

// ---- conversation state ----------------------------------------------------
// One turn per question. Each streamed agent event updates the turn it
// belongs to, so the trace fills in step by step as the backend works.

function applyEvent(turn, event) {
  switch (event.type) {
    case 'tool_call':
      return { ...turn, steps: [...turn.steps, { id: event.id, tool: event.tool, input: event.input, status: 'running' }] }
    case 'tool_result':
      return {
        ...turn,
        steps: turn.steps.map((s) =>
          s.id === event.id
            ? { ...s, status: event.is_error ? 'error' : 'done', output: event.output, sources: event.sources }
            : s,
        ),
      }
    case 'answer':
      return { ...turn, answer: { text: event.text, completed: event.completed }, status: 'done' }
    case 'error':
      return { ...turn, status: 'error', error: event.message }
    default:
      return turn
  }
}

function reducer(turns, action) {
  const update = (fn) => turns.map((t) => (t.id === action.turnId ? fn(t) : t))
  switch (action.type) {
    case 'start':
      return [...turns, { id: action.turnId, query: action.query, steps: [], answer: null, status: 'streaming', error: null }]
    case 'event':
      return update((t) => applyEvent(t, action.event))
    case 'finish':
      // the stream closed; if no answer or error event arrived, say so
      return update((t) =>
        t.status === 'streaming' ? { ...t, status: 'error', error: 'The response ended before an answer arrived.' } : t,
      )
    case 'fail':
      return update((t) => ({ ...t, status: 'error', error: action.message }))
    case 'stop':
      return update((t) => ({ ...t, status: 'stopped' }))
    default:
      return turns
  }
}

// ---- formatting helpers ------------------------------------------------------

function prettyExpression(expr) {
  return expr.replace(/\*\*/g, '^').replace(/\*/g, '×').replace(/\//g, '÷')
}

function prettyNumber(output) {
  const n = Number(output)
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : output
}

// ---- components ----------------------------------------------------------------

function SearchStep({ step }) {
  const query = step.input?.query
  const sources = step.sources ?? []
  return (
    <>
      <p className="step-line">
        {step.status === 'running' ? 'Searching the guidelines for ' : 'Searched the guidelines for '}
        <q>{query}</q>
      </p>
      {step.status === 'done' && sources.length === 0 && <p className="step-note">No matching passages.</p>}
      {sources.length > 0 && (
        <details className="passages">
          <summary>
            Read {sources.length} {sources.length === 1 ? 'passage' : 'passages'}
          </summary>
          <ul>
            {sources.map((src, i) => (
              <li key={i}>
                <p className="passage-title">
                  {src.title}
                  {src.section && <span className="passage-section">, {src.section}</span>}
                </p>
                <p className="passage-text">{src.content}</p>
                {src.citation_url?.startsWith('http') && (
                  <a href={src.citation_url} target="_blank" rel="noreferrer">
                    Open source
                  </a>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  )
}

function CalculateStep({ step }) {
  const expr = prettyExpression(step.input?.expression ?? '')
  if (step.status === 'running') return <p className="step-line">Calculating {expr}</p>
  if (step.status === 'error' || step.output?.startsWith('Error')) {
    return <p className="step-line">Couldn’t calculate {expr}</p>
  }
  return (
    <p className="equation">
      {expr} <span className="equals">=</span> <strong>{prettyNumber(step.output)}</strong>
    </p>
  )
}

function Step({ step }) {
  const kind = step.tool === 'retrieve_docs' ? 'search' : step.tool === 'calculate' ? 'calc' : 'other'
  return (
    <li className={`step step-${kind} is-${step.status}`}>
      {kind === 'search' && <SearchStep step={step} />}
      {kind === 'calc' && <CalculateStep step={step} />}
      {kind === 'other' && <p className="step-line">Called {step.tool}</p>}
      {step.status === 'error' && <p className="step-error">{step.output}</p>}
    </li>
  )
}

function Turn({ turn }) {
  const thinking = turn.status === 'streaming' && turn.steps.every((s) => s.status !== 'running')
  return (
    <article className="turn" aria-busy={turn.status === 'streaming'}>
      <h2 className="question">{turn.query}</h2>

      {(turn.steps.length > 0 || thinking) && (
        <ol className="trace" aria-label="What the assistant did">
          {turn.steps.map((step) => (
            <Step key={step.id} step={step} />
          ))}
          {thinking && (
            <li className="step step-thinking is-running">
              <p className="step-line">{turn.steps.length === 0 ? 'Reading your question' : 'Reviewing the results'}</p>
            </li>
          )}
        </ol>
      )}

      <div aria-live="polite">
        {turn.answer && (
          <div className="answer">
            <ReactMarkdown>{turn.answer.text}</ReactMarkdown>
            {!turn.answer.completed && (
              <p className="notice">The assistant ran out of reasoning steps before finishing. Try a more specific question.</p>
            )}
          </div>
        )}
        {turn.status === 'error' && <p className="notice notice-error">{turn.error}</p>}
        {turn.status === 'stopped' && <p className="notice">Stopped.</p>}
      </div>
    </article>
  )
}

export default function App() {
  const [turns, dispatch] = useReducer(reducer, [])
  const [draft, setDraft] = useState('')
  const [backendUp, setBackendUp] = useState(null)
  const abortRef = useRef(null)
  const nextId = useRef(1)
  const endRef = useRef(null)

  const busy = turns.at(-1)?.status === 'streaming'

  useEffect(() => {
    fetch('/api/health')
      .then((res) => setBackendUp(res.ok))
      .catch(() => setBackendUp(false))
  }, [])

  // keep the newest step in view as the trace grows
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    endRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'end' })
  }, [turns])

  async function ask(text) {
    const query = text.trim()
    if (!query || busy) return
    const turnId = nextId.current++
    dispatch({ type: 'start', turnId, query })
    setDraft('')

    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamAsk(query, { signal: controller.signal, onEvent: (event) => dispatch({ type: 'event', turnId, event }) })
      dispatch({ type: 'finish', turnId })
    } catch (err) {
      if (err.name === 'AbortError') dispatch({ type: 'stop', turnId })
      else if (err instanceof TypeError) {
        dispatch({ type: 'fail', turnId, message: 'Couldn’t reach the backend. Check that it’s running on port 8000.' })
      } else dispatch({ type: 'fail', turnId, message: err.message })
    } finally {
      abortRef.current = null
    }
  }

  return (
    <div className="app">
      <header className="masthead">
        <h1>Fitness &amp; Nutrition Assistant</h1>
        <p className="lede">Answers come from CDC, NIH and USDA guidance. Every search and calculation is shown.</p>
        {backendUp === false && (
          <p className="notice notice-error">Can’t reach the backend. Start it with <code>docker compose up</code>.</p>
        )}
      </header>

      <main className="conversation">
        {turns.length === 0 ? (
          <section className="empty" aria-label="Example questions">
            <p>Ask about exercise, nutrition, sleep or hydration. Try one of these:</p>
            <ul>
              {EXAMPLES.map((q) => (
                <li key={q}>
                  <button type="button" className="example" onClick={() => ask(q)}>
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          turns.map((turn) => <Turn key={turn.id} turn={turn} />)
        )}
        <div ref={endRef} />
      </main>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          ask(draft)
        }}
      >
        <label htmlFor="question" className="visually-hidden">
          Your question
        </label>
        <input
          id="question"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask a question"
          autoComplete="off"
        />
        {busy ? (
          <button type="button" className="button-secondary" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={!draft.trim()}>
            Ask
          </button>
        )}
      </form>
    </div>
  )
}
