"""Speech for the hub: the same voice the greeting uses.

Server-side on purpose. The page can speak with whatever voice the browser happens to
have, and on most systems that is a robotic one; the product says its lines in
Christopher's voice, so the synthesis has to happen where the voice lives.
"""
from __future__ import annotations

import asyncio
import io

VOICE = "en-US-ChristopherNeural"
RATE = "-5%"
MAX_CHARS = 1200


def available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


async def _synthesize(text: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


def speak(text: str) -> bytes:
    """Return mp3 bytes, or b'' when synthesis produced nothing.

    A short retry: edge-tts occasionally returns an empty stream on the first call,
    and silence is a worse answer than one more attempt.
    """
    clean = (text or "").strip()
    if not clean:
        return b""
    clean = clean[:MAX_CHARS]
    for _ in range(2):
        try:
            audio = asyncio.run(_synthesize(clean))
        except Exception:  # noqa: BLE001 - the caller reports «no voice» instead of a trace
            audio = b""
        if len(audio) > 1200:
            return audio
    return b""
