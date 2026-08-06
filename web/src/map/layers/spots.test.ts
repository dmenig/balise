/**
 * Layer specs are data, so the paint expressions are unit-testable against feature states
 * (docs/13). This is the guard on "a stale free must never look free".
 */
import { describe, expect, it } from 'vitest'
import {
  COLOURS,
  KIND_COLOURS,
  boatFilter,
  combineFilters,
  kindFilter,
  spotColour,
  spotKindColour,
  spotKindGlyph,
  spotsLayer,
} from './spots'

type Json = ReturnType<typeof JSON.parse>

/** Minimal evaluator for the `case`/`==`/`>=`/`coalesce`/`feature-state` subset we use. */
function evaluate(expression: Json, state: Record<string, unknown>): unknown {
  if (!Array.isArray(expression)) return expression
  const [operator, ...args] = expression as [string, ...Json[]]
  switch (operator) {
    case 'feature-state':
      return state[args[0] as string]
    case 'get':
      return state[args[0] as string]
    case 'coalesce': {
      for (const arg of args) {
        const value = evaluate(arg, state)
        if (value !== undefined && value !== null) return value
      }
      return null
    }
    case '==':
      return evaluate(args[0], state) === evaluate(args[1], state)
    case 'match': {
      const subject = evaluate(args[0], state)
      for (let index = 1; index + 1 < args.length; index += 2) {
        if (subject === args[index]) return evaluate(args[index + 1], state)
      }
      return evaluate(args[args.length - 1], state)
    }
    case '>=':
      return Number(evaluate(args[0], state)) >= Number(evaluate(args[1], state))
    case 'case': {
      for (let index = 0; index + 1 < args.length; index += 2) {
        if (evaluate(args[index], state)) return evaluate(args[index + 1], state)
      }
      return evaluate(args[args.length - 1], state)
    }
    default:
      throw new Error(`unsupported operator ${operator}`)
  }
}

describe('the UI seam (docs/06 §A/S5)', () => {
  it('renders every spot by kind in v1, because feature-state is never set', () => {
    // No `setFeatureState` call exists in v1, so the expression always takes the neutral branch.
    expect(evaluate(spotColour, { kind: 'mooring_buoy' })).toBe(KIND_COLOURS.mooring_buoy)
    expect(evaluate(spotColour, { kind: 'berth' })).toBe(KIND_COLOURS.berth)
    expect(evaluate(spotColour, { kind: 'anchorage' })).toBe(KIND_COLOURS.anchorage)
    expect(evaluate(spotColour, { kind: 'quoi' })).toBe(COLOURS.unknown)
  })

  it('is already written in its final v2 form, so switching on availability is wiring only', () => {
    expect(evaluate(spotColour, { kind: 'berth', state: 'free', confidence: 0.86 })).toBe(
      COLOURS.free,
    )
    expect(evaluate(spotColour, { kind: 'berth', state: 'free', confidence: 0.6 })).toBe(
      COLOURS.freeSoft,
    )
    expect(evaluate(spotColour, { kind: 'berth', state: 'occupied', confidence: 0.7 })).toBe(
      COLOURS.occupied,
    )
    // An unknown state falls back to the kind colour, exactly like v1.
    expect(evaluate(spotColour, { kind: 'berth', state: 'unknown', confidence: 0 })).toBe(
      KIND_COLOURS.berth,
    )
  })

  it('carries a non-colour channel for the kind, from tile data not feature-state', () => {
    expect(evaluate(spotKindGlyph, { kind: 'mooring_buoy' })).toBe('○')
    expect(evaluate(spotKindGlyph, { kind: 'anchorage' })).toBe('⚓')
    expect(evaluate(spotKindColour, { kind: 'pile' })).toBe(KIND_COLOURS.pile)
  })
})

describe('boat filters keep spots that fit', () => {
  it('keeps a spot with unknown limits and drops one that is too shallow', () => {
    const filter = boatFilter(1.8) as Json
    expect(filter).not.toBeNull()
    const clause = (filter as Json[])[1] as Json
    expect(evaluateFilter(clause, {})).toBe(true)
    expect(evaluateFilter(clause, { max_draft_m: 2.4 })).toBe(true)
    expect(evaluateFilter(clause, { max_draft_m: 1.2 })).toBe(false)
  })

  it('returns null when the sailor set no boat constraints', () => {
    expect(boatFilter(undefined, undefined)).toBeNull()
    expect(kindFilter([])).toBeNull()
    expect(combineFilters(null, null)).toBeNull()
  })

  it('combines the kind and boat filters under a single `all`', () => {
    const combined = combineFilters(kindFilter(['mooring_buoy']), boatFilter(2)) as Json[]
    expect(combined[0]).toBe('all')
    expect(combined).toHaveLength(3)
  })
})

describe('layer wiring', () => {
  it('reads status from feature-state, never from tile attributes (ADR-0002)', () => {
    expect(JSON.stringify(spotsLayer.paint)).toContain('feature-state')
    expect(JSON.stringify(spotsLayer.paint)).not.toContain('"get","state"')
  })
})

function evaluateFilter(expression: Json, properties: Record<string, unknown>): boolean {
  const [operator, ...args] = expression as [string, ...Json[]]
  if (operator === 'any') return args.some((arg) => evaluateFilter(arg, properties))
  if (operator === 'all') return args.every((arg) => evaluateFilter(arg, properties))
  if (operator === '!') return !evaluateFilter(args[0], properties)
  if (operator === 'has') return (args[0] as string) in properties
  if (operator === '>=') {
    const left = evaluate(args[0], properties)
    return Number(left ?? 99) >= Number(args[1])
  }
  return Boolean(evaluate(expression, properties))
}
