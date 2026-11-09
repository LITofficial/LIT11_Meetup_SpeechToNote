"""Probe only locally uploaded media in a separate bounded process."""
import json
import sys
import av


def probe(path):
    with av.open(path, options={"protocol_whitelist": "file"}) as container:
        formats = set(container.format.name.split(","))
        if not formats.intersection({"wav", "mp3", "mov", "mp4", "m4a"}):
            raise ValueError("unsupported container")
        audio = list(container.streams.audio)
        if not audio or list(container.streams.video):
            raise ValueError("not an audio file")
        stream = audio[0]
        if stream.codec_context.name not in {"aac", "mp3", "mp3float", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_u8"}:
            raise ValueError("unsupported codec")
        # Decode a real frame rather than trusting extension or metadata alone.
        frame = next(container.decode(stream), None)
        if frame is None or frame.samples <= 0:
            raise ValueError("empty audio")
        seconds = (float(stream.duration * stream.time_base) if stream.duration
                   else float(container.duration or 0) / av.time_base)
        if seconds <= 0:
            raise ValueError("unknown duration")
        suffix = ".wav" if "wav" in formats else ".mp3" if "mp3" in formats else ".m4a"
        return {"duration_ms": max(1, round(seconds * 1000)), "suffix": suffix}


if __name__ == "__main__":
    try:
        print(json.dumps(probe(sys.argv[1])))
    except Exception:
        # Never expose user paths or decoder output to API/logs.
        sys.exit(2)
