# Entity.ID conference booth loop (v3)

A **40 second**, **seamless**, **silent** **1920×1080** background video for the Entity.ID conference booth. Play it on loop in fullscreen behind the booth.

Entity.ID is **The Universal Verified Facts Identifier** for companies, NGOs, DAOs, AI agents, and jurisdictions.

![Entity.ID booth loop poster](entityid-booth/poster.png)

## Files

| File | Role |
|------|------|
| [`entityid-booth/entityid-booth-loop-v3-1080p.mp4`](entityid-booth/entityid-booth-loop-v3-1080p.mp4) | Booth playback master (~49.5 MB, 30 fps, no audio) |
| [`entityid-booth/entityid-booth-loop-v3-720p.mp4`](entityid-booth/entityid-booth-loop-v3-720p.mp4) | Lighter preview copy (~6.7 MB) |
| [`entityid-booth/poster.png`](entityid-booth/poster.png) | Title-frame still |
| [`entityid-booth/src/build_loop_v3.py`](entityid-booth/src/build_loop_v3.py) | Render script |

**SHA-256 (1080p):** `925e940f410044a66e1ba52d2d4706e3166d4c38b8937e3b5d611278dc339f4b`

## Scene list (in order)

1. **Network hubs** with real entity IDs:
   - AI Agents and DAOs
   - Delaware (DE) and Companies
   - Wyoming (WY) and NGOs
   - United States (US)
2. **Stats** (from [entity.id](https://entity.id)):
   - 2,935,661 registered entities
   - 311 active jurisdictions
   - 226,467 verifiable entities
3. **Tagline:** Unified · Verifiable · Interoperable
4. **Title:** “Every entity. One verifiable identity.” with **Entity.ID**
5. **CTA:** “Get your ID → app.entity.id” with a QR code to [https://app.entity.id](https://app.entity.id)

## Playback

Use any player that can loop a file fullscreen. Examples:

```bash
mpv --loop=inf --fs entityid-booth/entityid-booth-loop-v3-1080p.mp4
```

In **VLC**, open the 1080p file and enable **Repeat** (loop), then fullscreen.

## Re-render

From the repo root, with [ffmpeg](https://ffmpeg.org/), [Pillow](https://python-pillow.org/), [numpy](https://numpy.org/), and [qrcode](https://pypi.org/project/qrcode/) installed, and the **Inter** font available on your system:

```bash
python entityid-booth/src/build_loop_v3.py
```

The script writes the loop video and related outputs; see the script for paths and options.
