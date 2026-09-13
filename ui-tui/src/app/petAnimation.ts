import type { PetState } from './usePet.js'

/** Cadence used when the gateway did not send a usable `frameMs`. */
export const FRAME_MS = 160

export interface PetFrameSet {
  count: number
  frameMs?: number
}

export interface PetAnimationStep {
  /** Cursor to feed back into the next call. */
  cursor: number
  /** Delay before the next tick. */
  delayMs: number
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
 * to tick again. Mirrors `agent/pet/state.py::next_frame_step`.
 *
 * Every row loops; what separates them is the cadence the gateway sends with
 * the frames (`idle` breathes at roughly one loop every four seconds, the rows
 * that report live work stay near one second). The null index is the branch
 * that matters here: a state whose frames are still loading must keep the
 * painted frame up rather than blank the pet.
 */
export function nextAnimationStep(state: PetState, cursor: number, frames: PetFrameSet | null): PetAnimationStep {
  const count = frames?.count ?? 0

  // Nothing cached for this state yet: hold the painted frame and look again.
  if (count < 1) {
    return { cursor, delayMs: FRAME_MS, index: null }
  }

  const index = cursor % count

  return { cursor: index + 1, delayMs: frameDelayMs(frames?.frameMs), index }
}
