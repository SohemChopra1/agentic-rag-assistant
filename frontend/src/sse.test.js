// Run with: npm test  (Node's built-in test runner, no extra dependencies)
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createSSEParser } from './sse.js'

// Exactly what sse-starlette sends: \r\n line endings, a ping comment,
// and a multi-byte character (×) to catch splits inside it.
const BODY =
  'event: tool_call\r\ndata: {"type":"tool_call","tool":"calculate","input":{"expression":"80 × 1.2"}}\r\n\r\n' +
  ': ping - 2026-10-14 20:00:00\r\n\r\n' +
  'event: tool_result\r\ndata: {"type":"tool_result","output":"96.0"}\r\n\r\n' +
  'event: answer\r\ndata: {"type":"answer","text":"96 g"}\r\n\r\n'

const EXPECTED = [
  { event: 'tool_call', data: '{"type":"tool_call","tool":"calculate","input":{"expression":"80 × 1.2"}}' },
  { event: 'tool_result', data: '{"type":"tool_result","output":"96.0"}' },
  { event: 'answer', data: '{"type":"answer","text":"96 g"}' },
]

function parseInChunks(chunks) {
  const events = []
  const parser = createSSEParser((e) => events.push(e))
  chunks.forEach((c) => parser.push(c))
  parser.end()
  return events
}

test('parses a whole body delivered at once', () => {
  assert.deepEqual(parseInChunks([BODY]), EXPECTED)
})

test('gives the same result however the network splits the body', () => {
  // every possible two-way split, including between \r and \n
  for (let i = 1; i < BODY.length; i++) {
    assert.deepEqual(parseInChunks([BODY.slice(0, i), BODY.slice(i)]), EXPECTED, `split at index ${i}`)
  }
})

test('handles one character per chunk', () => {
  assert.deepEqual(parseInChunks([...BODY]), EXPECTED)
})

test('joins multi-line data with newlines', () => {
  assert.deepEqual(parseInChunks(['data: line one\ndata: line two\n\n']), [
    { event: 'message', data: 'line one\nline two' },
  ])
})

test('flushes a final event that has no trailing blank line', () => {
  assert.deepEqual(parseInChunks(['event: answer\ndata: {}']), [{ event: 'answer', data: '{}' }])
})

test('ignores comment-only blocks', () => {
  assert.deepEqual(parseInChunks([': ping\r\n\r\n']), [])
})
