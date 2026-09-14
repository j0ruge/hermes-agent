import { describe, expect, it } from 'vitest'

import { FRAME_MS, frameDelayMs, nextAnimationStep } from '../app/petAnimation.js'
import type { PetState } from '../app/usePet.js'

const frames = (count: number, frameMs?: number) => ({ count, frameMs })

// Walk the policy the way the hook does: paint, carry the cursor.
const play = (state: PetState, count: number, ticks: number) => {
  const painted: Array<number | null> = []
  let cursor = 0

  for (let i = 0; i < ticks; i += 1) {
    const step = nextAnimationStep(state, cursor, frames(count, 100))

    painted.push(step.index)
    cursor = step.cursor
  }

  return painted
}

describe('nextAnimationStep', () => {
  it('paints nothing and retries while the frames are still loading', () => {
    expect(nextAnimationStep('idle', 3, null)).toEqual({ cursor: 3, delayMs: FRAME_MS, index: null })
  })

  it('treats an empty frame set as still loading', () => {
    expect(nextAnimationStep('run', 0, frames(0))).toEqual({ cursor: 0, delayMs: FRAME_MS, index: null })
  })

  it.each<PetState>(['idle', 'run', 'review', 'waiting', 'wave', 'jump', 'failed'])('keeps %s looping', state => {
    expect(play(state, 3, 7)).toEqual([0, 1, 2, 0, 1, 2, 0])
  })

  it.each([1, 2, 6, 8])('closes the loop whatever the frame count (%i)', count => {
    expect(play('idle', count, count * 2)).toEqual([...Array(count).keys(), ...Array(count).keys()])
  })

  it('gives a frame the pet declared quick its own shorter delay', () => {
    // A blink is an event of ~150ms. On a breathing row every other frame is a
    // beat of the breath, and holding the blink that long reads as sleep.
    const breathing = { count: 6, frameMs: 800, frameMsByIndex: [923, 923, 923, 923, 185, 923] }

    expect(nextAnimationStep('idle', 4, breathing).delayMs).toBe(185)
    expect(nextAnimationStep('idle', 0, breathing).delayMs).toBe(923)
  })

  it('falls back to the row cadence for a frame the list does not cover', () => {
    expect(nextAnimationStep('idle', 5, { count: 6, frameMs: 800, frameMsByIndex: [185] }).delayMs).toBe(800)
  })

  it('paces the tick with the frameMs the gateway sent', () => {
    // The gateway derives it per state, so `idle` arrives slow (it breathes)
    // and the rows that report live work arrive fast. The hook just obeys.
    expect(nextAnimationStep('idle', 0, frames(6, 733)).delayMs).toBe(733)
    expect(nextAnimationStep('run', 0, frames(6, 183)).delayMs).toBe(183)
  })
})

describe('frameDelayMs', () => {
  it('uses a usable gateway cadence verbatim', () => {
    expect(frameDelayMs(733.33)).toBe(733.33)
  })

  it.each([undefined, 0, -5, Number.NaN, Number.POSITIVE_INFINITY])(
    'falls back to the default cadence for %s',
    frameMs => {
      expect(frameDelayMs(frameMs)).toBe(FRAME_MS)
    }
  )
})
