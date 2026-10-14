// The only module that talks to the backend. Writes carry one Idempotency-Key per user
// operation; an uncertain outcome is resolved by asking the server, never by assuming.

import type { ActionResult, ApiErrorBody, RequestRecord } from './types'

const TIMEOUT_MS = 10000

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly retryable: boolean
  readonly details: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.code = body.code
    this.status = status
    this.retryable = body.retryable
    this.details = body.details
  }
}

/** The request may or may not have been saved; resend it with the same key to find out. */
export class UncertainError extends Error {
  constructor() {
    super('网络中断，无法确认本次操作是否已保存。请重试同一操作。')
  }
}

export interface PendingWrite {
  key: string
  method: 'POST' | 'PUT' | 'DELETE'
  path: string
  body?: unknown
  expectedVersion?: number
}

async function parse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    if (body?.error) throw new ApiError(response.status, body.error)
    throw new ApiError(response.status, {
      code: 'INTERNAL_ERROR',
      message: '服务暂时不可用。',
      details: {},
      retryable: response.status >= 500,
    })
  }
  return body as T
}

export async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  return parse<T>(response)
}

export async function ensureVisitor(): Promise<{ current_session_id: string | null }> {
  const response = await fetch('/api/v1/visitors', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  return parse(response)
}

export function newWrite(
  method: PendingWrite['method'],
  path: string,
  body?: unknown,
  expectedVersion?: number,
): PendingWrite {
  return { key: crypto.randomUUID(), method, path, body, expectedVersion }
}

async function lookup(key: string): Promise<ActionResult | null> {
  try {
    const record = await get<RequestRecord>(`/api/v1/requests/${key}`)
    if (record.error) throw new ApiError(record.original_http_status, record.error)
    return record.result
  } catch (error) {
    if (error instanceof ApiError && error.code === 'REQUEST_NOT_FOUND') return null
    throw error
  }
}

/** Send (or resend) one write. Success is reported only after the server confirms it. */
export async function send<T>(write: PendingWrite): Promise<ActionResult<T>> {
  const headers: Record<string, string> = { 'Idempotency-Key': write.key }
  if (write.body !== undefined) headers['Content-Type'] = 'application/json'
  if (write.expectedVersion !== undefined) {
    headers['X-Expected-State-Version'] = String(write.expectedVersion)
  }
  let response: Response
  try {
    response = await fetch(write.path, {
      method: write.method,
      credentials: 'same-origin',
      headers,
      body: write.body === undefined ? undefined : JSON.stringify(write.body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
  } catch {
    const saved = await lookup(write.key).catch(() => null)
    if (saved) return saved as ActionResult<T>
    throw new UncertainError()
  }
  return parse<ActionResult<T>>(response)
}
