---
name: video-compare-slider
description: Compare two videos with a draggable wipe slider in the browser - video A on the left, video B on the right, a handle on a vertical line starting at 50% - with play, pause, scrub and frame stepping kept in sync on both. Use this whenever the user wants to compare two videos, renders, encodes, grades, film looks, cuts or versions side by side, see what changed between two video files, A/B a before/after in motion, or judge two takes against each other, even if they don't say "slider" or "compare". Not for still images alone or for computed metrics (PSNR, SSIM, VMAF).
---

# Video compare slider

Opens a local page in which both videos lie on top of each other at the same size and a vertical divider with a
handle wipes between them: A shows left of the divider, B right of it. The handle starts in the middle. One control
bar plays, pauses, scrubs and steps both videos together.

Built on [img-comparison-slider](https://github.com/sneas/img-comparison-slider) (MIT, vendored unmodified in
`assets/`, license in `assets/LICENSE-img-comparison-slider`) for the wipe, plus the page's own sync code. Both browser
engines on macOS decode two 2880x2160 H.264 streams in hardware, so no native app is needed.

## Run it

```bash
python3 ~/.claude/skills/video-compare-slider/scripts/vcompare.py A.mp4 B.mp4
```

- **Safari (the default on macOS): file mode.** The script hard-links both videos and the page into a private folder
  (`/private/tmp/vcompare-<uid>/<session>/`, no extra disk space, nothing written next to the videos), opens it in
  Safari and returns at once. This is the fastest way for WebKit to read big files: it even plays ProRes 422 HQ in real
  time.
- **Firefox, Chrome, or videos on another volume: http mode.** A small local server (127.0.0.1, HTTP Range support for
  seeking, it serves only the page and the two videos) runs until it is stopped. Run it as a **background task**,
  give the user the URL it prints, and stop the task when they are done (it removes its session folder).
- Options: `--browser safari|firefox|chrome|default|none` (none: only print the URL), `--mode auto|file|http`,
  `--start SECONDS`, `--fps N` (frame stepping; default A's frame rate), `--port N`, `--cleanup`.
- If the user's machine routes work through a job queue or wants it niced, wrap the command the way they ask (a light,
  short job).

The script first prints what ffprobe says about both files (codec, pixel format, size, frame rate, length, bitrate)
and a note for anything that differs or won't play: different sizes, frame rates, lengths or color tags (a mismatch
of color tags makes the two sides look different for reasons that aren't in the pictures), ProRes outside Safari, or
4:2:2/4:4:4 H.264/HEVC. Pass these notes on to the user.

## Tell the user how to use it

| Control | Does |
|---|---|
| drag the handle | move the divider (only the handle drags) |
| Space, or a click on the picture | play / pause both |
| `,` `.` (or the ‹ › buttons) | one frame back / forward |
| Left / Right (Shift: x10) | 1 s back / forward |
| Home / End | start / end |
| `[` `]` (Shift: 10%) | move the divider by 1% |
| `0` | divider back to 50% |
| `s` | swap sides |
| `m` | mute (the sound is A's) |
| `f` | fullscreen |

The scrub bar, the timecode (HH:MM:SS:FF) and the frame number are in the bar; the file names sit in the top corners.
The bar and the pointer fade out after 2.5 s without mouse activity (for uninterrupted viewing, e.g. full screen); moving
the mouse brings them back, the keys work without bringing them back.

## What to expect from the sync

- **Paused, stepped or scrubbed:** both sides always show exactly the same frame (both are seeked to the middle of the
  frame and the page waits until both have arrived).
- **Playing:** both start in the same instant; B follows A. The bar shows how far B's frame is from A's (`B +0f`).
  Chrome and Firefox nudge B's speed by up to 5% to stay on A's frame; Safari, which stalls when a video's speed
  changes, re-seeks B when it drifts 4 or more frames. In tests on two 2880x2160 H.264 renders both engines stayed on
  the same frame. To check on the user's machine, open the page's URL with `#selftest` appended: it plays 10 s and
  shows the drift, dropped frames and frame accuracy.
- A stall on one side (slow disk, a seek) holds the other until both can play.

## When a video doesn't play

The page shows a message when a browser loads a video as audio only (no picture) or can't load it at all.

- **ProRes:** only Safari plays it. Otherwise compare a proxy, made with ffmpeg:
  `ffmpeg -i IN.mov -c:v libx264 -crf 14 -pix_fmt yuv420p -g 24 -c:a aac -b:a 320k -movflags +faststart OUT.mp4`.
  Make proxies of **both** sides the same way, so the comparison stays fair, and use a low CRF (10-14) when grain or
  fine detail is what is being compared: a proxy smooths grain. Ask before running long transcodes.
- **Frame-exact playback or a native tool:** `brew install video-compare` (pixop/video-compare, GPL-2.0, FFmpeg and
  SDL2), then `video-compare -W A B`. Its split follows the mouse instead of a handle, and it plays no sound.

## Blind duels in the slider (with the visual-ab-duel skill)

To pick among several videos blind, run the visual-ab-duel tournament and show each match in the slider instead of
as stills:

1. Read the visual-ab-duel skill and follow its protocol (one pair per message, nothing that identifies the options).
2. Its `candidates.json` needs, per candidate, an `image` (one still at the same moment from each video, 8-bit: the
   tool makes its match pictures from them) and a `clip`: the **full video**. Put the current version in.
3. `duel.py --state DIR init candidates.json --no-open`, then for every match:
   `python3 ~/.claude/skills/video-compare-slider/scripts/duel_slider.py --state DIR` opens the current pair blind,
   labelled "match M, picture 1" (left) and "picture 2" (right), and prints only the match and the URL. (With
   `--mode http` it keeps serving: run it in the background and stop it after the answer.)
4. The user answers 1, 2 or too close; `record`/`defer`/`reshuffle` as the duel skill says, then `next --no-open` and
   `duel_slider.py` again. Skip the duel's `moments` and `clips` (the user can scrub to any moment in the slider, and
   `clips` copies the whole files). At the end `reveal`.

Don't run vcompare.py on duel candidates by hand in front of the user: it prints the file names.

## Housekeeping

File-mode session folders hold hard links: a video deleted by the user keeps its data on disk while a link to it
exists. The script removes sessions older than 6 hours whenever it runs; `vcompare.py --cleanup` removes them all
(do it when the user deletes videos that were compared, or at the end of a review session).
