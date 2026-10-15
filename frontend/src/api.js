import { createSSEParser } from './sse.js'

// POST /ask/stream and call onEvent(payload) for each agent event as it
// arrives: tool_call, tool_result, answer, or error (see backend
// app/agent/loop.py for the payload shapes). Resolves when the stream ends.
// Throws on a non-2xx response (e.g. 503 when an API key is missing) with
// the backend's error detail as the message.
export async function streamAsk(query, { onEvent, signal }) {
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ query }),
    signal,
  })

  if (!res.ok) {
    let detail = null
    try {
      detail = (await res.json()).detail
    } catch {
      // body wasn't JSON — fall through to the generic message
    }
    throw new Error(typeof detail === 'string' ? detail : `The request failed with HTTP ${res.status}.`)
  }

  const parser = createSSEParser(({ event, data }) => {
    if (event !== 'ping') onEvent(JSON.parse(data))
  })
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    parser.push(value)
  }
  parser.end()
}
