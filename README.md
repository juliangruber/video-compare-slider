# video-compare-slider

A [Claude Code](https://claude.com/claude-code) skill to compare two videos with a wipe slider in the browser: video A
on the left, video B on the right, and a handle on a vertical line (starting at 50%) that you drag to wipe between
them. Both videos play, pause, scrub and step frame by frame together.

Made for judging film looks and renders of a music video: two 4K renders with heavy film grain, side by side, in sync.

## Install

```sh
git clone https://github.com/juliangruber/video-compare-slider ~/.claude/skills/video-compare-slider
```

Claude Code picks it up as a skill: ask it to compare two videos. Or run the launcher yourself:

```sh
python3 ~/.claude/skills/video-compare-slider/scripts/vcompare.py A.mp4 B.mp4
```

Needs Python 3.7+ (standard library only) and, optionally, `ffprobe` (codec check, frame rate).

## How it works

- **Safari (the default on macOS):** both videos are hard-linked next to the page in a private temp folder (no copies,
  nothing written next to your files) and opened as `file://`. WebKit reads big local files fastest this way: it plays
  two 2880x2160 high-bitrate H.264 files, even ProRes 422 HQ, in real time.
- **Firefox / Chrome (`--browser firefox`), or videos on another volume:** a small local server with HTTP Range
  support (needed for seeking) on 127.0.0.1, serving only the page and the two videos, until stopped.
- **Sync:** paused, stepped or scrubbed, both sides show exactly the same frame. While playing, Chrome and Firefox nudge
  B's speed to stay on A's frame; Safari re-seeks B when it drifts. Open the page with `#selftest` to measure it on
  your machine.
- **The wipe** is [img-comparison-slider](https://github.com/sneas/img-comparison-slider) 8.0.7 by Dmytro Snisarenko
  (MIT), vendored unmodified in `assets/` with its license.

## Controls

| Control | Does |
|---|---|
| drag the divider (anywhere along it) | wipe between A and B |
| Space, or click the picture | play / pause both |
| `,` `.` | one frame back / forward |
| Left / Right (Shift: x10) | 1 s back / forward |
| Home / End | start / end |
| `[` `]` (Shift: 10%) | move the divider by 1% |
| `0` | divider back to 50% |
| `s` | swap sides |
| `m` | mute (the sound is A's) |
| `f` | fullscreen |

The control bar fades out after 2.5 s without mouse activity; moving the mouse brings it back.

## Options

```
vcompare.py A B [--browser safari|firefox|chrome|default|none] [--mode auto|file|http] [--port N]
                [--start SECONDS] [--fps N] [--label-a TEXT --label-b TEXT [--blind]] [--cleanup]
```

`--blind` shows only the labels (no file names or file info), for blind comparisons; `scripts/duel_slider.py` shows
the current match of a blind A/B tournament this way. See [SKILL.md](SKILL.md) for everything Claude is told.

## License

MIT (this skill). `assets/img-comparison-slider.js` is MIT too, see `assets/LICENSE-img-comparison-slider`.
