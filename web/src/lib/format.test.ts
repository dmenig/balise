import { describe, expect, it } from 'vitest'
import {
  ageLabel,
  bucketClass,
  compass,
  distanceNm,
  knots,
  price,
  spotSubtitle,
  statusLabel,
} from './format'
import type { Status } from './types'

function status(patch: Partial<Status> = {}): Status {
  return {
    state: 'free',
    confidence: 0.86,
    bucket: 'confirmed',
    as_of: '2026-08-06T13:41:30Z',
    source_kind: 'port_feed',
    age_seconds: 154,
    ...patch,
  }
}

describe('statusLabel — the honesty string (docs/06)', () => {
  it('shows state, source and age for a confirmed free spot', () => {
    expect(statusLabel(status())).toBe('Libre — Port, il y a 3 min')
  })

  it('downgrades the wording when confidence is only probable', () => {
    expect(
      statusLabel(
        status({
          confidence: 0.6,
          bucket: 'probable',
          source_kind: 'community',
          age_seconds: 2400,
        }),
      ),
    ).toBe('Probablement libre — Communauté, il y a 40 min')
  })

  it('never names a source for an unknown state', () => {
    expect(statusLabel(status({ state: 'unknown', bucket: 'unknown', confidence: 0 }))).toBe(
      'Disponibilité inconnue',
    )
  })

  it('labels an occupied spot with its source and age', () => {
    expect(
      statusLabel(status({ state: 'occupied', source_kind: 'community', age_seconds: 7200 })),
    ).toBe('Occupé — Communauté, il y a 2 h')
  })
})

describe('units are the sailor’s (docs/09 rule 6)', () => {
  it('formats knots, prices and compass sectors', () => {
    expect(knots(12.4)).toBe('12 kt')
    expect(price(2800)).toBe('28.00 €/nuit')
    expect(compass(200)).toBe('SSW')
    expect(compass(null)).toBe('—')
  })

  it('reads ages the way a sailor speaks', () => {
    expect(ageLabel(30)).toBe("à l'instant")
    expect(ageLabel(154)).toBe('il y a 3 min')
    expect(ageLabel(7200)).toBe('il y a 2 h')
    expect(ageLabel(200_000)).toBe('il y a 2 j')
  })
})

describe('bucketClass', () => {
  it('separates confirmed free from probable free, and collapses the rest', () => {
    expect(bucketClass('confirmed', 'free')).toBe('pin-free')
    expect(bucketClass('probable', 'free')).toBe('pin-free-soft')
    expect(bucketClass('confirmed', 'occupied')).toBe('pin-occupied')
    expect(bucketClass('unknown', 'unknown')).toBe('pin-unknown')
  })
})

describe('the list subtitle tells two identical buoys apart (docs/02)', () => {
  const buoy = {
    kind: 'mooring_buoy',
    depth_m: null,
    max_loa_m: null,
    max_draft_m: null,
    visitor: true,
    status: null,
  }

  it('leads with the distance from the boat when the browser knows it', () => {
    // Port-Navalo → a buoy ~0.55 NM north-east.
    const nm = distanceNm([-2.9182, 47.5432], [-2.9081, 47.5493])
    expect(nm).toBeCloseTo(0.55, 1)
    expect(spotSubtitle(buoy, nm)).toBe('0.55 NM · visiteurs')
  })

  it('falls back to what the referential knows when there is no position', () => {
    expect(spotSubtitle(buoy)).toBe('visiteurs')
    expect(spotSubtitle({ ...buoy, visitor: false })).toBe('Dimensions non renseignées')
  })

  it('shows whole tenths past a mile so the number stays readable', () => {
    expect(spotSubtitle({ ...buoy, depth_m: 2.4 }, 12.34)).toBe(
      '12.3 NM · 2.4 m de sonde · visiteurs',
    )
  })
})
