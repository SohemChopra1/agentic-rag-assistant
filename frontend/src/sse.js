// Incremental Server-Sent Events parser.
//
// The browser's EventSource only supports GET, and /ask/stream is a POST,
// so the stream is read with fetch() and parsed here. Network chunks don't
// align with events: one read() can hold half an event or three of them,
// and sse-starlette ends lines with \r\n, which can itself be split across
// two reads. The parser buffers until a blank line closes an event.
// Spec: https://html.spec.whatwg.org/multipage/server-sent-events.html

export function createSSEParser(onEvent) {
  let buffer = ''

  function dispatch(block) {
    let event = 'message'
    const data = []
    for (const line of block.split('\n')) {
      if (line === '' || line.startsWith(':')) continue // ':' starts a comment
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      let value = colon === -1 ? '' : line.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') event = value
      else if (field === 'data') data.push(value)
    }
    if (data.length > 0) onEvent({ event, data: data.join('\n') })
  }

  return {
    push(chunk) {
      let text = buffer + chunk
      // A trailing '\r' may be the first half of a '\r\n' that arrives in
      // the next chunk. Normalizing it now would turn that '\r\n' into two
      // newlines, which reads as an event boundary that doesn't exist.
      let pendingCR = ''
      if (text.endsWith('\r')) {
        pendingCR = '\r'
        text = text.slice(0, -1)
      }
      text = text.replace(/\r\n?/g, '\n')

      const blocks = text.split('\n\n')
      buffer = blocks.pop() + pendingCR // the last piece is an incomplete event
      blocks.forEach(dispatch)
    },

    end() {
      const rest = buffer.replace(/\r\n?/g, '\n').trim()
      buffer = ''
      if (rest) dispatch(rest)
    },
  }
}
