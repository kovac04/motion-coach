export type VoiceUsed = 'elevenlabs' | 'browser' | 'disabled'

export interface VoiceResult {
  voice: VoiceUsed
  ttsMs: number // backend synthesis time (ElevenLabs)
  totalMs: number // fetch + playback-start
}

let currentAudio: HTMLAudioElement | null = null

/** Stop any in-flight speech so sets never overlap. */
export function stopSpeaking(): void {
  if (currentAudio) {
    try {
      currentAudio.pause()
      currentAudio.src = ''
    } catch {
      /* ignore */
    }
    currentAudio = null
  }
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

/** Resolves when playback actually begins (or fails), not when it ends. */
function playBlobUrl(url: string): Promise<void> {
  return new Promise((resolve) => {
    const audio = new Audio(url)
    currentAudio = audio
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      if (currentAudio === audio) currentAudio = null
      URL.revokeObjectURL(url)
      resolve()
    }
    audio.onplaying = finish
    audio.onended = finish
    audio.onerror = finish
    void audio.play().catch(finish)
  })
}

function speakInBrowser(text: string): Promise<void> {
  if (!('speechSynthesis' in window)) return Promise.resolve()
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = 1.0
  utterance.pitch = 1.0
  window.speechSynthesis.speak(utterance)
  return Promise.resolve()
}

/**
 * Try backend ElevenLabs first; fall back to the browser voice. Never throws.
 * Returns measured latency for the developer overlay.
 */
export async function playCoaching(text: string, voiceMode: string): Promise<VoiceResult> {
  stopSpeaking()
  const started = performance.now()
  if (voiceMode === 'disabled') return { voice: 'disabled', ttsMs: 0, totalMs: 0 }

  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (res.ok) {
      const ttsMs = Number(res.headers.get('X-TTS-Ms') ?? '0')
      const blob = await res.blob()
      await playBlobUrl(URL.createObjectURL(blob))
      return { voice: 'elevenlabs', ttsMs, totalMs: performance.now() - started }
    }
  } catch {
    // fall through to browser voice
  }

  await speakInBrowser(text)
  return { voice: 'browser', ttsMs: 0, totalMs: performance.now() - started }
}
