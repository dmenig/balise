import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'
import type { Status } from '../lib/types'

function status(patch: Partial<Status> = {}): Status {
  return {
    state: 'free',
    confidence: 0.86,
    bucket: 'confirmed',
    as_of: '2026-08-06T13:41:30Z',
    source_kind: 'port_feed',
    age_seconds: 120,
    ...patch,
  }
}

describe('StatusBadge', () => {
  it('never shows a state without its source and age', () => {
    render(<StatusBadge status={status()} />)
    const badge = screen.getByTestId('status-badge')
    expect(badge).toHaveAttribute('data-state', 'free')
    expect(badge.textContent).toContain('Libre')
    expect(badge.textContent).toContain('Port')
    expect(badge.textContent).toContain('il y a 2 min')
  })

  it('says "probablement libre" below the confirmed bucket', () => {
    render(
      <StatusBadge
        status={status({ confidence: 0.55, bucket: 'probable', source_kind: 'community' })}
      />,
    )
    expect(screen.getByTestId('status-badge').textContent).toContain('Probablement libre')
  })

  it('shows no source at all for an unknown state', () => {
    render(<StatusBadge status={status({ state: 'unknown', bucket: 'unknown', confidence: 0 })} />)
    const badge = screen.getByTestId('status-badge')
    expect(badge.textContent).toContain('Disponibilité inconnue')
    expect(badge.textContent).not.toContain('Port')
  })
})
