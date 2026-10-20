import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, UncertainError, newWrite, send } from '../src/api/client'
import { json, stubFetch } from './fixtures'

afterEach(() => vi.unstubAllGlobals())

const committed = {
  request_id: 'r',
  session_id: 's',
  business_status: 'COMMITTED',
  state_changed: true,
  state_version_before: 1,
  result_state_version: 2,
  phase_after: 'INVESTIGATION',
  saved_at: '2026-10-12T00:00:00Z',
  data: {},
}

describe('write protocol', () => {
  it('sends the idempotency key and expected version with JSON', async () => {
    const fetchMock = stubFetch({ 'POST /api/v1/x': () => json(201, committed) })
    const write = newWrite('POST', '/api/v1/x', { action_id: 'A01' }, 7)
    await send(write)
    const headers = fetchMock.mock.calls[0][1]!.headers as Record<string, string>
    expect(headers['Idempotency-Key']).toBe(write.key)
    expect(headers['X-Expected-State-Version']).toBe('7')
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('recovers a committed result after the connection drops', async () => {
    const write = newWrite('POST', '/api/v1/x', {}, 1)
    stubFetch({
      'POST /api/v1/x': () => Promise.reject(new TypeError('network')),
      [`GET /api/v1/requests/${write.key}`]: () =>
        json(200, { status: 'COMMITTED', original_http_status: 201, result: committed }),
    })
    await expect(send(write)).resolves.toEqual(committed)
  })

  it('reports a stored rejection found after the connection drops', async () => {
    const write = newWrite('POST', '/api/v1/x', {}, 1)
    const rejection = { code: 'STATE_VERSION_CONFLICT', message: '已更新', details: {} }
    stubFetch({
      'POST /api/v1/x': () => Promise.reject(new TypeError('network')),
      [`GET /api/v1/requests/${write.key}`]: () =>
        json(200, {
          status: 'REJECTED',
          original_http_status: 409,
          result: null,
          error: { ...rejection, retryable: false },
        }),
    })
    const failure = await send(write).catch((error) => error)
    expect(failure).toBeInstanceOf(ApiError)
    expect([failure.code, failure.status]).toEqual(['STATE_VERSION_CONFLICT', 409])
  })

  it('never claims success when the outcome is unknown or the database failed', async () => {
    const write = newWrite('POST', '/api/v1/x', {}, 1)
    stubFetch({
      'POST /api/v1/x': () => Promise.reject(new TypeError('network')),
      [`GET /api/v1/requests/${write.key}`]: () =>
        json(404, {
          error: { code: 'REQUEST_NOT_FOUND', message: '', details: {}, retryable: false },
        }),
    })
    await expect(send(write)).rejects.toBeInstanceOf(UncertainError)
    stubFetch({
      'POST /api/v1/x': () =>
        json(503, {
          error: {
            code: 'PERSISTENCE_UNAVAILABLE',
            message: '存档服务暂不可用',
            details: {},
            retryable: true,
          },
        }),
    })
    const failure = await send(write).catch((error) => error)
    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.retryable).toBe(true)
  })
})
