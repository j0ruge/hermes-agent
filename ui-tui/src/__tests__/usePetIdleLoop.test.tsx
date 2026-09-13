import { PassThrough } from 'stream'

import { renderSync } from '@hermes/ink'
import React, { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GatewayProvider } from '../app/gatewayContext.js'
import { resetOverlayState } from '../app/overlayStore.js'
import { $petFlash } from '../app/petFlashStore.js'
import { patchTurnState, resetTurnState } from '../app/turnStore.js'
import { resetUiState } from '../app/uiStore.js'
import { usePet } from '../app/usePet.js'
import type { PetGrid } from '../components/petSprite.js'

// A distinguishable one-cell grid per frame, so a painted frame can be named
// by identity instead of by pixel matching.
const grid = (n: number): PetGrid => [[[n, n, n, 255, n, n, n, 255]]]

const FRAME_MS = 100

/** The `pet.cells` payload the gateway returns per terminal capability. */
const cellsPayload = (state: string, count: number) => ({
  enabled: true,
  frameMs: FRAME_MS,
  frames: Array.from({ length: count }, (_, i) => grid(i)),
  scale: 1,
  slug: 'gabiru',
  state
})

const kittyPayload = (state: string, count: number) => ({
  color: '#000001',
  enabled: true,
  frameMs: FRAME_MS,
  frames: Array.from({ length: count }, (_, i) => `«${state}:${i}»`),
  graphics: 'kitty',
  imageId: 7,
  placeholder: ['**'],
  scale: 1,
  slug: 'gabiru',
  state
})

const mounted: Array<() => void> = []

interface PetHarness {
  /** Frames painted so far, as `state:index` labels, oldest first. */
  painted: () => string[]
  unmount: () => void
}

/**
 * Mount the real hook through Ink with a stub gateway. The cells path is read
 * back from the grid the hook hands the renderer; the kitty path is read back
 * from the transmit escapes it writes to the terminal out-of-band — the same
 * two ways a user would see a frame.
 */
const mountPet = (mode: 'cells' | 'kitty', count = 3): PetHarness => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()

  Object.assign(stdout, { columns: 40, isTTY: false, rows: 12 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })

  // This Ink fork's `useStdout().write` — the out-of-band channel the kitty
  // path transmits each frame on — goes straight to `process.stdout`, so that
  // is where the transmits have to be read back from.
  let written = ''

  vi.spyOn(process.stdout, 'write').mockImplementation(chunk => {
    written += String(chunk)

    return true
  })

  const payload = mode === 'kitty' ? kittyPayload : cellsPayload

  const request = vi.fn(async (method: string, params?: { state?: string }) =>
    method === 'pet.info.meta'
      ? { enabled: true, scale: 1, slug: 'gabiru', spritesheetRevision: 'r1' }
      : payload(params?.state ?? 'idle', count)
  )

  const gridPaints: string[] = []
  let state = 'idle'

  const Probe = () => {
    const pet = usePet()

    useEffect(() => {
      const index = pet.grid?.[0]?.[0]?.[0]

      if (typeof index === 'number' && gridPaints.at(-1) !== `${state}:${index}`) {
        gridPaints.push(`${state}:${index}`)
      }
    })

    return null
  }

  const instance = renderSync(
    <GatewayProvider value={{ gw: { request }, rpc: () => Promise.resolve(null) } as never}>
      <Probe />
    </GatewayProvider>,
    {
      patchConsole: false,
      stderr: stderr as NodeJS.WriteStream,
      stdin: stdin as NodeJS.ReadStream,
      stdout: stdout as NodeJS.WriteStream
    }
  )

  const unmount = () => {
    instance.unmount()
    instance.cleanup()
  }

  mounted.push(unmount)

  return {
    painted: () =>
      mode === 'kitty' ? [...written.matchAll(/«([a-z]+:\d)»/g)].map(match => match[1] ?? '') : gridPaints,
    unmount
  }
}

/**
 * Drive the animation forward, then let the gateway promises and React's
 * scheduler (which runs on real macrotasks, not on the faked timers) settle so
 * the painted frame is observable.
 */
const advance = async (ms: number) => {
  await vi.advanceTimersByTimeAsync(ms)
  await new Promise(resolve => setImmediate(resolve))
  await new Promise(resolve => setImmediate(resolve))
}

const enterRun = async () => {
  patchTurnState({ tools: [{ name: 'bash' }] as never })
  await advance(0)
}

const enterIdle = async () => {
  patchTurnState({ tools: [] })
  await advance(0)
}

describe('usePet animation loop', () => {
  beforeEach(() => {
    // Only the hook's own scheduling is faked; React's scheduler keeps its real
    // macrotasks so renders still flush between ticks.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
    resetTurnState()
    resetUiState()
    resetOverlayState()
    $petFlash.set(null)
  })

  afterEach(() => {
    while (mounted.length) {
      mounted.pop()?.()
    }

    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('plays the idle row once and then rests on the first frame', async () => {
    const pet = mountPet('cells')

    await advance(0)
    expect(pet.painted()).toEqual(['idle:0'])

    await advance(FRAME_MS * 3)
    expect(pet.painted()).toEqual(['idle:0', 'idle:1', 'idle:2', 'idle:0'])
  })

  it('never restarts idle, however long the agent sits still', async () => {
    const pet = mountPet('cells')

    await advance(FRAME_MS * 100)

    expect(pet.painted()).toEqual(['idle:0', 'idle:1', 'idle:2', 'idle:0'])
  })

  it('rests on the first frame in the kitty path too', async () => {
    const pet = mountPet('kitty')

    await advance(FRAME_MS * 100)

    expect(pet.painted()).toEqual(['idle:0', 'idle:1', 'idle:2', 'idle:0'])
  })

  it.each([1, 2, 6])('settles after one cycle whatever the frame count (%i)', async count => {
    const pet = mountPet('kitty', count)

    await advance(FRAME_MS * 100)

    expect(pet.painted()).toHaveLength(count + 1)
    expect(pet.painted().at(-1)).toBe('idle:0')
  })

  it('keeps looping while a tool is running', async () => {
    const pet = mountPet('kitty')

    await advance(FRAME_MS * 100)
    await enterRun()
    await advance(FRAME_MS * 6)

    expect(pet.painted().slice(4)).toEqual(['run:0', 'run:1', 'run:2', 'run:0', 'run:1', 'run:2', 'run:0'])
  })

  it('grants exactly one fresh cycle when the agent falls back to idle', async () => {
    const pet = mountPet('kitty')

    await advance(FRAME_MS * 100)
    await enterRun()
    await advance(FRAME_MS * 2)
    await enterIdle()
    await advance(FRAME_MS * 100)

    expect(pet.painted().filter(label => label.startsWith('idle'))).toEqual([
      'idle:0',
      'idle:1',
      'idle:2',
      'idle:0',
      'idle:0',
      'idle:1',
      'idle:2',
      'idle:0'
    ])
  })

  it('arms a single animation timer across a state change', async () => {
    const pet = mountPet('kitty')

    await advance(FRAME_MS * 100)
    await enterRun()
    await advance(FRAME_MS)

    const before = pet.painted().length

    await advance(FRAME_MS)

    // A leaked second loop would paint two frames per tick.
    expect(pet.painted().length - before).toBe(1)
  })

  it('paces the frames with the frameMs the gateway sent', async () => {
    const pet = mountPet('kitty')

    // Measure from the first painted frame; the mount itself costs a tick of
    // gateway round-trip. 100ms is the payload's frameMs, not the 160ms default.
    await advance(0)
    expect(pet.painted()).toEqual(['idle:0'])

    await advance(FRAME_MS - 1)
    expect(pet.painted()).toEqual(['idle:0'])

    await advance(1)
    expect(pet.painted()).toEqual(['idle:0', 'idle:1'])
  })

  it('stops painting once the hook unmounts', async () => {
    const pet = mountPet('kitty')

    await enterRun()
    await advance(FRAME_MS * 2)

    const before = pet.painted().length

    pet.unmount()
    await advance(FRAME_MS * 50)

    expect(pet.painted()).toHaveLength(before)
  })
})
