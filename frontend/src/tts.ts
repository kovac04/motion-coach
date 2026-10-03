export type VoiceUsed = 'elevenlabs' | 'browser' | 'disabled'

function playBlobUrl(url: string): Promise<void> {
  return new Promise((resolve) => {
    const audio = new Audio(url)
    audio.onended = () => {
      URL.revokeObjectURL(url)
      resolve()
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      resolve()
    }
    void audio.play().catch(() => resolve())
  })
}

function speakInBrowser(text: string): VoiceUsed {
  if (!('speechSynthesis' in window)) return 'disabled'
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = 1.0
  utterance.pitch = 1.0
  window.speechSynthesis.speak(utterance)
  return 'browser'
}

/**
 * Try backend ElevenLabs first; fall back to the browser voice. Never throws —
 * the demo must survive a TTS outage.
 */
export async function playCoaching(text: string, voiceMode: string): Promise<VoiceUsed> {
  if (voiceMode === 'disabled') return 'disabled'

  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (res.ok) {
      const blob = await res.blob()
      await playBlobUrl(URL.createObjectURL(blob))
      return 'elevenlabs'
    }
  } catch {
    // fall through to browser voice
  }

  return speakInBrowser(text)
}

export function stopSpeaking(): void {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}
