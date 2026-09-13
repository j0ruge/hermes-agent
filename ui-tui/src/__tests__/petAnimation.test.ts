import { describe, expect, it } from 'vitest'

import { FRAME_MS, frameDelayMs, nextAnimationStep } from '../app/petAnimation.js'
import type { PetState } from '../app/usePet.js'

const frames = (count: number, frameMs?: number) => ({ count, frameMs })

// Walk the policy the way the hook does: paint, carry the cursor, stop when it
// reports no next tick. Bounded so a looping state can never hang the test.
const play = (state: PetState, count: number, ticks = 24) => {
  const painted: Array<number | null> = []
  let cursor = 0
  let settled = false

  for (let i = 0; i < ticks; i += 1) {
    const step = nextAnimationStep(state, cursor, frames(count, 100))

    painted.push(step.index)
    cursor = step.cursor

    if (step.delayMs === null) {
      settled = true

      break
    }
  }

  return { cursor, painted, settled }
}

describe('nextAnimationStep', () => {
  it('paints nothing and retries while the frames are still loading', () => {
    expect(nextAnimationStep('idle', 3, null)).toEqual({ cursor: 3, delayMs: FRAME_MS, index: null })
  })

  it('treats an empty frame set as still loading', () => {
    expect(nextAnimationStep('run', 0, frames(0))).toEqual({ cursor: 0, delayMs: FRAME_MS, index: null })
  })

  it('plays idle through exactly one cycle and then rests on the first frame', () => {
    expect(play('idle', 4)).toEqual({ cursor: 4, painted: [0, 1, 2, 3, 0], settled: true })
  })

  it('rests idle on the first frame for any cursor past the cycle', () => {
    expect(nextAnimationStep('idle', 4, frames(4))).toEqual({ cursor: 4, delayMs: null, index: 0 })
    expect(nextAnimationStep('idle', 99, frames(4))).toEqual({ cursor: 4, delayMs: null, index: 0 })
  })

  it.each([1, 2, 5, 9])('settles idle after one cycle of %i frames', count => {
    const { painted, settled } = play('idle', count)

    expect(settled).toBe(true)
    expect(painted.at(-1)).toBe(0)
    expect(painted).toHaveLength(count + 1)
  })

  it.each<PetState>(['run', 'review', 'waiting', 'wave', 'jump', 'failed'])('keeps %s looping', state => {
    const { painted, settled } = play(state, 3, 7)

    expect(settled).toBe(false)
    expect(painted).toEqual([0, 1, 2, 0, 1, 2, 0])
  })

  it('paces the tick with the frameMs the gateway sent', () => {
    expect(nextAnimationStep('run', 0, frames(3, 83)).delayMs).toBe(83)
    expect(nextAnimationStep('idle', 0, frames(3, 83)).delayMs).toBe(83)
  })
})

describe('frameDelayMs', () => {
  it('uses a usable gateway cadence verbatim', () => {
    expect(frameDelayMs(83.5)).toBe(83.5)
  })

  it.each([undefined, 0, -5, Number.NaN, Number.POSITIVE_INFINITY])(
    'falls back to the default cadence for %s',
    frameMs => {
      expect(frameDelayMs(frameMs)).toBe(FRAME_MS)
    }
  )
})
