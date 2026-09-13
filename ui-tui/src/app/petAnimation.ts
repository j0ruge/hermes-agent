import type { PetState } from './usePet.js'

/** Cadence used when the gateway did not send a usable `frameMs`. */
export const FRAME_MS = 160

/**
 * States that play once and then go quiet. `idle` is the pet's resting pose —
 * its row is specified as a calm, low-distraction beat, so looping it forever
 * turns the corner of the terminal into a permanent flicker during long
 * sessions. Every other state is a live read-out of what the agent is doing and
 * keeps cycling for as long as it holds.
 */
const ONE_SHOT_STATES = new Set<PetState>(['idle'])

export interface PetFrameSet {
  count: number
  frameMs?: number
}

export interface PetAnimationStep {
  /** Cursor to feed back into the next call. */
  cursor: number
  /** Delay before the next tick, or null once the animation has settled. */
  delayMs: number | null
  /** Frame to paint now, or null while this state's frames are still loading. */
  index: number | null
}

/** Trust the gateway's cadence only when it is a real, positive duration. */
export function frameDelayMs(frameMs?: number): number {
  return typeof frameMs === 'number' && Number.isFinite(frameMs) && frameMs > 0 ? frameMs : FRAME_MS
}

/**
 * The whole animation policy, as a pure step: given the state, the cursor the
 * previous tick handed back and the frames on hand, say what to paint and when
 * (or whether) to tick again.
 *
 * A one-shot state walks 0..n-1, paints the first frame once more and settles
 * there — `delayMs: null` tells the caller to stop scheduling, so the pet holds
 * frame one instead of freezing on the last frame of the cycle. Re-entering the
 * state resets the cursor, which is what buys it a fresh single cycle.
 */
export function nextAnimationStep(state: PetState, cursor: number, frames: PetFrameSet | null): PetAnimationStep {
  const count = frames?.count ?? 0

  // Nothing cached for this state yet: hold the painted frame and look again.
  if (count < 1) {
    return { cursor, delayMs: FRAME_MS, index: null }
  }

  const delayMs = frameDelayMs(frames?.frameMs)

  if (!ONE_SHOT_STATES.has(state)) {
    const index = cursor % count

    return { cursor: index + 1, delayMs, index }
  }

  if (cursor < count) {
    return { cursor: cursor + 1, delayMs, index: cursor }
  }

  return { cursor: count, delayMs: null, index: 0 }
}
