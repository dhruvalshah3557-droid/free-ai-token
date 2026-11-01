#!/usr/bin/env python3
import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"
PUBLIC = ROOT / "public"
JOBS_PATH = OUTPUT / "jobs.json"

OUTPUT.mkdir(parents=True, exist_ok=True)
PUBLIC.mkdir(parents=True, exist_ok=True)

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
LOGO = ASSETS / "logo.png"

SIZES = {
    "reel": (1080, 1920),
    "square": (1080, 1080),
    "landscape": (1920, 1080),
}

PRODUCTS = {
    "ring": {
        "label": "Engagement Rings",
        "headline": "A colour that lasts forever",
        "line": "Custom GIA-certified coloured diamond rings",
        "hue": 38,
    },
    "pendant": {
        "label": "Pendants",
        "headline": "Colour worn close to the heart",
        "line": "Fine coloured diamond pendants, made to order",
        "hue": 320,
    },
    "earring": {
        "label": "Earrings",
        "headline": "Light, captured in colour",
        "line": "Statement coloured diamond earrings",
        "hue": 210,
    },
    "necklace": {
        "label": "Necklaces",
        "headline": "Elegance in every facet",
        "line": "Hand-selected fancy colour diamond necklaces",
        "hue": 45,
    },
    "bracelet": {
        "label": "Bracelets",
        "headline": "Warm colour, lifetime craft",
        "line": "Coloured diamond bracelets with free worldwide shipping",
        "hue": 25,
    },
    "diamond": {
        "label": "Fancy Colour Diamonds",
        "headline": "Pink. Yellow. Blue. Rare.",
        "line": "GIA-certified fancy colour diamonds, Bangkok atelier",
        "hue": 330,
    },
}

jobs_lock = threading.Lock()
jobs = {}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_jobs():
    global jobs
    if JOBS_PATH.exists():
        try:
            jobs = json.loads(JOBS_PATH.read_text())
        except json.JSONDecodeError:
            jobs = {}


def save_jobs():
    JOBS_PATH.write_text(json.dumps(jobs, indent=2))


def slug(text):
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip()).strip("-").lower()
    return cleaned[:48] or "clip"


def escape_drawtext(text):
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\u2019")
        .replace("%", "%%")
    )


def clamp_duration(value):
    try:
        duration = int(value)
    except (TypeError, ValueError):
        duration = 10
    return max(6, min(duration, 20))


def public_base():
    return os.environ.get("PUBLIC_BASE", "").rstrip("/")


def video_urls(job):
    filename = job["filename"]
    base = public_base()
    path = f"/videos/{filename}"
    return {
        "url": f"{base}{path}" if base else path,
        "download_url": f"{base}{path}" if base else path,
    }


def build_prompt(product, headline, line, duration, size):
    spec = PRODUCTS[product]
    return (
        f"ColourDiam luxury {spec['label'].lower()} film, {duration}s {size}. "
        f"{headline}. {line}. Brand www.colourdiam.com. "
        "Dark atelier, gold light, diamond sparkle, cinematic jewelry commercial."
    )


def render_video(job_id):
    with jobs_lock:
        job = jobs[job_id]
        job["status"] = "rendering"
        job["updated_at"] = utc_now()
        save_jobs()

    product = job["product"]
    spec = PRODUCTS[product]
    width, height = SIZES[job["size"]]
    duration = job["duration"]
    headline = job["headline"]
    line = job["tagline"]
    cta = job["cta"]
    outfile = OUTPUT / job["filename"]
    hue = spec["hue"]
    fontsize = 52 if job["size"] == "landscape" else 56
    subsize = 26 if job["size"] == "landscape" else 28
    mid_y = int(height * 0.46)
    sub_y = int(height * 0.56)
    cta_y = int(height * 0.78)
    logo_w = 180 if job["size"] == "landscape" else 220
    has_logo = LOGO.exists()
    glow_w = max(320, int(width * 0.42))
    glow_h = max(220, int(height * 0.18))

    filter_complex = (
        f"color=c=0x0b0908:s={width}x{height}:d={duration}:r=24[bg];"
        f"color=c=0xd4af37:s={glow_w}x{glow_h}:d={duration}:r=24,format=rgba,"
        f"colorchannelmixer=aa=0.16,gblur=sigma=48[glow];"
        f"[bg][glow]overlay=(W-w)/2:(H-h)/2[lit];"
        f"[lit]hue=h={hue}:s=1.12,eq=contrast=1.08:saturation=1.08:brightness=0.02[toned];"
        f"[toned]drawbox=x=0:y=0:w={width}:h=8:color=0xd4af37@0.95:t=fill,"
        f"drawbox=x=0:y={height - 8}:w={width}:h=8:color=0xd4af37@0.95:t=fill[framed];"
        f"[framed]drawtext=fontfile={FONT_BOLD}:text='COLOURDIAM':"
        f"fontsize=28:fontcolor=0xf3e6c4:x=(w-text_w)/2:y={int(height * 0.18)}[brand];"
        f"[brand]drawtext=fontfile={FONT}:text='{escape_drawtext(spec['label'].upper())}':"
        f"fontsize=20:fontcolor=0xd4af37:x=(w-text_w)/2:y={int(height * 0.22)}[cat];"
        f"[cat]drawtext=fontfile={FONT_BOLD}:text='{escape_drawtext(headline)}':"
        f"fontsize={fontsize}:fontcolor=white:x=(w-text_w)/2:y={mid_y}[title];"
        f"[title]drawtext=fontfile={FONT}:text='{escape_drawtext(line)}':"
        f"fontsize={subsize}:fontcolor=0xe8dcc3:x=(w-text_w)/2:y={sub_y}[sub];"
        f"[sub]drawtext=fontfile={FONT_BOLD}:text='{escape_drawtext(cta)}':"
        f"fontsize=26:fontcolor=0x111111:box=1:boxcolor=0xd4af37@0.94:"
        f"boxborderw=14:x=(w-text_w)/2:y={cta_y}[cta];"
        f"[cta]drawtext=fontfile={FONT}:text='www.colourdiam.com':"
        f"fontsize=22:fontcolor=0xf3e6c4:x=(w-text_w)/2:y={cta_y + 64}[texted]"
    )
    if has_logo:
        filter_complex += (
            f";[2:v]scale={logo_w}:-1,format=rgba,colorchannelmixer=aa=0.96[logo];"
            f"[texted][logo]overlay=(W-w)/2:{int(height * 0.07)}:format=auto,format=yuv420p[outv]"
        )
    else:
        filter_complex += ";[texted]format=yuv420p[outv]"

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:d={duration}:r=24",
    ]
    if has_logo:
        cmd += ["-i", str(LOGO)]
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[outv]",
        "-map",
        "0:a",
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(outfile),
    ]

    started = time.time()
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0 or not outfile.exists() or outfile.stat().st_size < 1000:
            raise RuntimeError((completed.stderr or completed.stdout or "ffmpeg failed").strip())
        with jobs_lock:
            job = jobs[job_id]
            job["status"] = "ready"
            job["bytes"] = outfile.stat().st_size
            job["render_ms"] = int((time.time() - started) * 1000)
            job["updated_at"] = utc_now()
            job["error"] = None
            save_jobs()
    except Exception as err:
        with jobs_lock:
            job = jobs[job_id]
            job["status"] = "failed"
            job["error"] = str(err)[:800]
            job["updated_at"] = utc_now()
            save_jobs()


app = Flask(__name__, static_folder=str(PUBLIC), static_url_path="")
load_jobs()


@app.get("/")
def index():
    return send_from_directory(PUBLIC, "index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "brand": "ColourDiam", "site": "https://www.colourdiam.com"})


@app.get("/api/templates")
def templates():
    return jsonify(
        {
            "products": [
                {"id": key, **{k: v for k, v in value.items() if k != "hue"}}
                for key, value in PRODUCTS.items()
            ],
            "sizes": [
                {"id": "reel", "label": "Instagram / TikTok Reel", "width": 1080, "height": 1920},
                {"id": "square", "label": "Feed square", "width": 1080, "height": 1080},
                {"id": "landscape", "label": "YouTube / website", "width": 1920, "height": 1080},
            ],
            "brand": {
                "name": "ColourDiam",
                "url": "https://www.colourdiam.com",
                "promise": "Free shipping & returns · 100% money back · Lifetime warranty",
            },
        }
    )


@app.get("/api/videos")
def list_videos():
    with jobs_lock:
        items = [
            {**job, **video_urls(job)}
            for job in sorted(jobs.values(), key=lambda item: item.get("created_at", ""), reverse=True)
        ]
    return jsonify({"videos": items})


@app.get("/api/videos/<job_id>")
def get_video(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Video not found"}), 404
    return jsonify({**job, **video_urls(job)})


@app.post("/api/videos/generate")
def generate_video():
    body = request.get_json(silent=True) or {}
    product = (body.get("product") or "ring").strip().lower()
    if product not in PRODUCTS:
        return jsonify({"error": "Unknown product. Use ring, pendant, earring, necklace, bracelet, diamond."}), 400
    size = (body.get("size") or "reel").strip().lower()
    if size not in SIZES:
        return jsonify({"error": "Unknown size. Use reel, square, or landscape."}), 400
    spec = PRODUCTS[product]
    headline = (body.get("headline") or spec["headline"]).strip()[:80]
    tagline = (body.get("tagline") or spec["line"]).strip()[:120]
    cta = (body.get("cta") or "Shop colourdiam.com").strip()[:48]
    duration = clamp_duration(body.get("duration", 10))
    job_id = uuid.uuid4().hex[:12]
    filename = f"{job_id}-{slug(product)}-{size}.mp4"
    width, height = SIZES[size]
    job = {
        "id": job_id,
        "status": "queued",
        "brand": "ColourDiam",
        "product": product,
        "product_label": spec["label"],
        "headline": headline,
        "tagline": tagline,
        "cta": cta,
        "size": size,
        "width": width,
        "height": height,
        "duration": duration,
        "filename": filename,
        "prompt": build_prompt(product, headline, tagline, duration, size),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "error": None,
        "bytes": 0,
    }
    with jobs_lock:
        jobs[job_id] = job
        save_jobs()
    threading.Thread(target=render_video, args=(job_id,), daemon=True).start()
    return jsonify({**job, **video_urls(job)}), 202


@app.get("/videos/<path:filename>")
def serve_video(filename):
    safe = Path(filename).name
    path = OUTPUT / safe
    if not path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(OUTPUT, safe, mimetype="video/mp4", as_attachment=False)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), threaded=True)
