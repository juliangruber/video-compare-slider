#!/usr/bin/env python3
"""Show the current match of a visual-ab-duel tournament (~/.claude/skills/visual-ab-duel) in the compare slider:
picture 1 on the left, picture 2 on the right, labelled only "match M, picture N" (vcompare.py --blind).

  duel_slider.py --state DIR [vcompare.py options, e.g. --browser firefox]

Each duel candidate needs "clip": its full video (the duel's own `clips` command copies the files, too slow for long,
large videos). Run the duel's `next --no-open` first, then this. It prints only the match and the page's URL, never
the candidates' names or files (the user must not learn which is which before the duel's `reveal`).
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = sys.argv[1:]
    if "--state" not in args or args.index("--state") + 1 >= len(args):
        sys.exit(__doc__)
    i = args.index("--state")
    state, rest = args[i + 1], args[:i] + args[i + 2:]
    st = json.load(open(os.path.join(state, "state.json")))
    if not st.get("current"):
        sys.exit("duel_slider: no match open (run the duel's next first)")
    m = st["match"]
    clips = [st["info"][c].get("clip") for c in st["current"]]
    if not all(clips):
        sys.exit("duel_slider: a candidate has no clip (its full video)")
    # (file mode returns at once; http mode keeps serving until stopped: run it in the background then)
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "vcompare.py"), clips[0], clips[1], "--blind",
                          "--label-a", "match %d, picture 1" % m, "--label-b", "match %d, picture 2" % m, *rest],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    shown = False
    for line in p.stdout:                      # pass on only the URL: the rest names the files
        if line.startswith(("file://", "http://")) and not shown:
            print("match %d: picture 1 left, picture 2 right: %s" % (m, line.strip()), flush=True)
            shown = True
    if p.wait() != 0 or not shown:
        sys.exit("duel_slider: the slider did not start (run vcompare.py on the pair yourself to see why, privately)")


if __name__ == "__main__":
    main()
