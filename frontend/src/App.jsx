import { useEffect, useState } from 'react'

// Phase 0 scaffold: confirms frontend <-> backend wiring works.
// Chat UI + SSE streaming land in Phase 4 — see ROADMAP.md.
function App() {
  const [status, setStatus] = useState('checking backend...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setStatus(`backend status: ${data.status}`))
      .catch(() => setStatus('backend unreachable'))
  }, [])

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>Agentic RAG Assistant</h1>
      <p>{status}</p>
    </div>
  )
}

export default App
