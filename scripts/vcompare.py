#!/usr/bin/env python3
"""Compare two videos with a wipe slider in the browser: A on the left, B on the right, a handle on a vertical line
(starts at 50%), both videos played, paused, scrubbed and stepped together.

  vcompare.py A B [--browser safari|firefox|chrome|default|none] [--mode auto|file|http] [--port 0]
                  [--start SECONDS] [--fps N] [--label-a TEXT --label-b TEXT [--blind]] [--cleanup]

--label-a/--label-b replace the file names on the page; --blind also leaves out everything that could tell the videos
apart besides the pictures (file info, file names in the title): for blind comparisons, e.g. with the
visual-ab-duel skill ("match 3, picture 1" / "match 3, picture 2").

Modes:
  file  (default for Safari) the page and hard links to both videos in a private temp folder, opened as file://.
        No server; nothing written next to the videos and no extra disk space. Safari plays even ProRes HQ in real
        time this way. The script returns at once; old session folders are swept on the next run (a hard link keeps a
        deleted video's data on disk until then: --cleanup removes them all).
  http  (Firefox/Chrome, or when a hard link isn't possible, e.g. another volume) a small local server on
        127.0.0.1 with HTTP Range support (needed for seeking), serving only the page and the two videos. Runs until
        Ctrl+C (run it in the background) and removes its session folder on exit.

Needs Python 3.7+ (stdlib only); ffprobe (optional) for the codec check and the frame rate.
"""
import argparse, json, mimetypes, os, re, shutil, signal, socket, subprocess, sys, tempfile, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")
# (on macOS /private/tmp: Safari reads file:// pages and media there; same volume as the home folder, so hard links work)
ROOT = os.path.join("/private/tmp" if sys.platform == "darwin" else tempfile.gettempdir(), "vcompare-%d" % os.getuid())
SWEEP_AFTER = 6 * 3600          # s: file-mode sessions older than this are removed on the next run
PROXY = "ffmpeg -i IN -c:v libx264 -crf 14 -pix_fmt yuv420p -g 24 -c:a aac -b:a 320k -movflags +faststart OUT.mp4"


# ------------------------------------------------------------------------------------------------ probing
def probe(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=codec_name,profile,pix_fmt,width,height,r_frame_rate,color_primaries,color_transfer,"
                              "color_space,color_range:format=duration,bit_rate", "-of", "json", path],
                             capture_output=True, text=True, timeout=30).stdout
        j = json.loads(out)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    s = (j.get("streams") or [{}])[0]
    f = j.get("format") or {}
    num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {"codec": s.get("codec_name"), "profile": s.get("profile"), "pix_fmt": s.get("pix_fmt"),
            "w": s.get("width"), "h": s.get("height"), "fps": round(fps, 3), "dur": float(f.get("duration") or 0),
            "mbps": round(int(f.get("bit_rate") or 0) / 1e6), "color": tuple(s.get(k) for k in
            ("color_primaries", "color_transfer", "color_space", "color_range"))}


def describe(p):
    if not p:
        return "?"
    return "%s %s %sx%s %sfps %.2fs %d Mb/s" % (p["codec"], p["pix_fmt"], p["w"], p["h"], p["fps"], p["dur"], p["mbps"])


def warnings(pa, pb, browser):
    w = []
    if pa and pb:
        if (pa["w"], pa["h"]) != (pb["w"], pb["h"]):
            w.append("the sizes differ (%sx%s vs %sx%s): both are scaled to the same frame" % (pa["w"], pa["h"], pb["w"], pb["h"]))
        if abs(pa["fps"] - pb["fps"]) > 0.01:
            w.append("the frame rates differ (%s vs %s): frame stepping follows A" % (pa["fps"], pb["fps"]))
        if abs(pa["dur"] - pb["dur"]) > 0.5:
            w.append("the lengths differ (%.2fs vs %.2fs): the timeline is the shorter one" % (pa["dur"], pb["dur"]))
        if pa["color"] != pb["color"]:
            w.append("the color tags differ (%s vs %s): the browser may show them differently for reasons that aren't in "
                     "the pictures" % (pa["color"], pb["color"]))
    for name, p in (("A", pa), ("B", pb)):
        if p and p["codec"] == "prores" and browser != "safari":
            w.append("%s is ProRes: only Safari plays it (or compare a proxy: %s)" % (name, PROXY))
        if p and p["pix_fmt"] and ("422" in p["pix_fmt"] or "444" in p["pix_fmt"]) and p["codec"] in ("h264", "hevc"):
            w.append("%s is %s %s: browsers may not decode 4:2:2/4:4:4 %s; if it shows no picture, compare a proxy" %
                     (name, p["codec"], p["pix_fmt"], p["codec"]))
    return w


# ------------------------------------------------------------------------------------------------ session folders
def sweep(all_=False):
    if not os.path.isdir(ROOT):
        return
    now = time.time()
    for d in os.listdir(ROOT):
        p = os.path.join(ROOT, d)
        if all_ or now - os.path.getmtime(p) > SWEEP_AFTER:
            shutil.rmtree(p, ignore_errors=True)


def page(session, cfg):
    html = open(os.path.join(ASSETS, "index.html"), encoding="utf-8").read()
    html = re.sub(r"/\*VC_CONFIG\*/.*?/\*END\*/", lambda m: json.dumps(cfg), html, count=1, flags=re.S)
    with open(os.path.join(session, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    shutil.copy(os.path.join(ASSETS, "img-comparison-slider.js"), session)


# ------------------------------------------------------------------------------------------------ http mode
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
FILES = {}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, socket.timeout)):
            return                                  # the browser dropped a connection: normal while seeking
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"                   # keep-alive: browsers fetch media in many range requests
    disable_nagle_algorithm = True

    def log_message(self, fmt, *args):
        pass

    def do_HEAD(self):
        self.send(head=True)

    def do_GET(self):
        self.send(head=False)

    def send(self, head):
        target = FILES.get(self.path.split("?", 1)[0])
        if target is None:
            self.send_error(404)
            return
        size = os.path.getsize(target)
        start, end, status = 0, size - 1, 200
        m = RANGE_RE.match((self.headers.get("Range") or "").strip())
        if m and (m.group(1) or m.group(2)):
            a, b = m.group(1), m.group(2)
            start, end = (max(0, size - int(b)), size - 1) if a == "" else (int(a), min(int(b), size - 1) if b else size - 1)
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-cache")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if head:
            return
        try:
            with open(target, "rb") as f:
                self.connection.sendfile(f, offset=start, count=end - start + 1)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass


# ------------------------------------------------------------------------------------------------ main
def open_url(url, browser):
    if browser == "none":
        return
    if sys.platform == "darwin" and browser in ("safari", "firefox", "chrome"):
        app = {"safari": "Safari", "firefox": "Firefox", "chrome": "Google Chrome"}[browser]
        if subprocess.run(["open", "-a", app, url]).returncode == 0:
            return
        print("could not open %s; opening the default browser" % app)
    webbrowser.open(url)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("a", nargs="?")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--browser", default="safari" if sys.platform == "darwin" else "default",
                    choices=["safari", "firefox", "chrome", "default", "none"])
    ap.add_argument("--mode", default="auto", choices=["auto", "file", "http"])
    ap.add_argument("--port", type=int, default=0, help="http mode: the port (default: a free one)")
    ap.add_argument("--start", type=float, default=0.0, help="start at this time (s)")
    ap.add_argument("--fps", type=float, default=0.0, help="frame rate for frame stepping (default: A's, else 24)")
    ap.add_argument("--label-a", help="label for A instead of its file name")
    ap.add_argument("--label-b", help="label for B instead of its file name")
    ap.add_argument("--blind", action="store_true", help="show only the labels: no file names or file info on the page")
    ap.add_argument("--cleanup", action="store_true", help="remove every session folder (and their hard links) and exit")
    args = ap.parse_args()
    if args.cleanup:
        sweep(all_=True)
        print("removed", ROOT)
        return
    if not (args.a and args.b):
        ap.error("give two videos")
    paths = [os.path.abspath(p) for p in (args.a, args.b)]
    for p in paths:
        if not os.path.isfile(p):
            sys.exit("no such file: %s" % p)
    pa, pb = probe(paths[0]), probe(paths[1])
    print("A  %s\n   %s\nB  %s\n   %s" % (paths[0], describe(pa), paths[1], describe(pb)))
    for w in warnings(pa, pb, args.browser):
        print("note:", w)
    fps = args.fps or (pa and pa["fps"]) or 24
    aspect = (pa["w"] / pa["h"]) if pa and pa["w"] and pa["h"] else 16 / 9

    sweep()
    os.makedirs(ROOT, mode=0o700, exist_ok=True)
    session = tempfile.mkdtemp(prefix=time.strftime("%Y%m%d-%H%M%S-"), dir=ROOT)
    exts = [os.path.splitext(p)[1].lower() or ".mp4" for p in paths]
    mode = args.mode
    if mode == "auto":
        mode = "file" if args.browser == "safari" else "http"
    if mode == "file":
        try:
            for name, p, e in zip("ab", paths, exts):
                os.link(p, os.path.join(session, name + e))      # (Safari refuses symlinks from file:// pages)
        except OSError as err:
            if args.mode == "file":
                sys.exit("can't hard-link the videos into %s (%s): use --mode http" % (session, err))
            print("note: can't hard-link the videos (%s): serving them over http instead" % err)
            mode = "http"
    cfg = {"a": {"name": args.label_a or os.path.basename(paths[0]), "info": "" if args.blind else describe(pa)},
           "b": {"name": args.label_b or os.path.basename(paths[1]), "info": "" if args.blind else describe(pb)},
           "fps": fps, "start": args.start, "aspect": aspect, "proxy": PROXY, "blind": args.blind}
    if mode == "file":
        cfg["a"]["src"], cfg["b"]["src"] = "a" + exts[0], "b" + exts[1]
        page(session, cfg)
        url = "file://" + os.path.join(session, "index.html")
        print(url)
        open_url(url, args.browser)
        return
    cfg["a"]["src"], cfg["b"]["src"] = "/a", "/b"
    page(session, cfg)
    mimetypes.add_type("video/mp4", ".mp4"); mimetypes.add_type("video/mp4", ".m4v")
    mimetypes.add_type("video/quicktime", ".mov")
    FILES.update({"/": os.path.join(session, "index.html"), "/index.html": os.path.join(session, "index.html"),
                  "/img-comparison-slider.js": os.path.join(session, "img-comparison-slider.js"),
                  "/a": paths[0], "/b": paths[1]})
    httpd = Server(("127.0.0.1", args.port), Handler)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print(url, flush=True)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    open_url(url, args.browser)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        shutil.rmtree(session, ignore_errors=True)


if __name__ == "__main__":
    main()
