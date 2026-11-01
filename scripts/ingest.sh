#!/usr/bin/env bash
# Reel Factory — ingest one raw clip. Mechanical steps only, no LLM needed.
# Usage: scripts/ingest.sh <path-to-raw-clip> <slug>
# Example: scripts/ingest.sh inbox/IMG_0011.MOV online-store
#
# Produces, in jobs/<date>-<slug>/:
#   probe.json      full ffprobe output
#   proxy.mp4       1080x1920, 30 fps CFR, H.264, SDR (what HyperFrames edits)
#   audio16k.wav    mono 16 kHz (what ASR reads)
#   silences.txt    pauses >= 0.4 s (cut candidates)
#   loudness.txt    integrated loudness of the voice
#   job.json        status "ingested" with verified input facts
# The raw file is moved to assets/raw/ and made read-only. Nothing is deleted.

set -euo pipefail

SRC="${1:?usage: ingest.sh <clip> <slug>}"
SLUG="${2:?usage: ingest.sh <clip> <slug>}"
DATE="$(date +%F)"
JOB="jobs/${DATE}-${SLUG}"
EXT="${SRC##*.}"
RAW="assets/raw/${DATE}-${SLUG}.${EXT}"

die() { echo "INGEST FAILED: $*" >&2; exit 1; }

[ -f "$SRC" ] || die "file not found: $SRC"
command -v ffmpeg >/dev/null || die "ffmpeg missing"
command -v ffprobe >/dev/null || die "ffprobe missing"
command -v node >/dev/null || die "node missing"

mkdir -p "$JOB" assets/raw

# 1. Move raw into place (never overwrite, never delete)
if [ -e "$RAW" ]; then
  echo "raw already in place: $RAW"
else
  mv -n "$SRC" "$RAW"
  chmod a-w "$RAW"
fi

# 2. Probe
ffprobe -v error -print_format json -show_format -show_streams "$RAW" > "$JOB/probe.json"

read -r VCODEC W H TRANSFER FPS DUR ROT HAS_AUDIO SIZE < <(node -e '
const p = require(process.argv[1]);
const v = p.streams.find(s => s.codec_type === "video");
const a = p.streams.some(s => s.codec_type === "audio");
if (!v) { console.log("NONE"); process.exit(0); }
const rot = Math.abs(Number(v.tags?.rotate ?? (v.side_data_list||[]).find(d => d.rotation !== undefined)?.rotation ?? 0));
const [n, d] = (v.avg_frame_rate || "0/1").split("/").map(Number);
console.log([v.codec_name, v.width, v.height, v.color_transfer || "unknown",
  (d ? n/d : 0).toFixed(2), Number(p.format.duration || 0).toFixed(3), rot, a ? 1 : 0,
  p.format.size || 0].join(" "));
' "$PWD/$JOB/probe.json")

[ "$VCODEC" = "NONE" ] && die "no video stream"
awk "BEGIN{exit !($DUR > 0)}" || die "zero duration"
[ "$HAS_AUDIO" = "1" ] || echo "WARNING: no audio stream — captions need a voiceover or script"

HDR=0
case "$TRANSFER" in arib-std-b67|smpte2084) HDR=1 ;; esac

echo "source: $VCODEC ${W}x${H} rot=${ROT} ${FPS}fps ${DUR}s transfer=${TRANSFER} hdr=${HDR} size=$((SIZE/1048576))MB"

# 3. Proxy: auto-rotate (ffmpeg default), tone-map if HDR, fill 1080x1920, constant 30 fps
FIT="scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=30"
if [ "$HDR" = "1" ]; then
  FILTERS="$(ffmpeg -hide_banner -filters 2>/dev/null || true)"
  grep -q " zscale " <<<"$FILTERS" \
    || die "HDR source but this ffmpeg has no zscale; install an ffmpeg built with libzimg, or reshoot with HDR Video off"
  VF="zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,${FIT}"
else
  VF="${FIT},format=yuv420p"
fi

ffmpeg -hide_banner -loglevel error -y -i "$RAW" -vf "$VF" \
  -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$JOB/proxy.mp4"

# 4. Audio for ASR, pauses, loudness
if [ "$HAS_AUDIO" = "1" ]; then
  ffmpeg -hide_banner -loglevel error -y -i "$JOB/proxy.mp4" -vn -ac 1 -ar 16000 "$JOB/audio16k.wav"
  ffmpeg -hide_banner -i "$JOB/audio16k.wav" -af silencedetect=noise=-35dB:d=0.4 -f null - 2>&1 \
    | grep -E "silence_(start|end)" > "$JOB/silences.txt" || true
  ffmpeg -hide_banner -i "$JOB/proxy.mp4" -af ebur128 -f null - 2>&1 \
    | grep -A1 "Integrated loudness" | tail -1 | sed 's/^ *//' > "$JOB/loudness.txt" || true
fi

# 5. Verify proxy
PDUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$JOB/proxy.mp4")
PDIM=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$JOB/proxy.mp4")
[ -s "$JOB/proxy.mp4" ] || die "proxy is empty"
[ "$PDIM" = "1080x1920" ] || die "proxy is $PDIM, expected 1080x1920"
awk "BEGIN{d=$PDUR-$DUR; if(d<0)d=-d; exit !(d < 0.2)}" || die "proxy duration $PDUR != source $DUR"

# 6. job.json (never overwrite an existing one)
if [ ! -e "$JOB/job.json" ]; then
  node -e '
const [id, raw, dur, fps, w, h, rot, audio, hdr, codec] = process.argv.slice(1);
const job = {
  id, status: "ingested",
  inputs: [{ path: raw, proxy: "proxy.mp4", duration: +dur, source_fps: +fps,
    resolution: `${w}x${h}`, rotation: +rot, codec, hdr: hdr === "1", audio: audio === "1", probed: true }],
  transcript: { path: "transcript.json", engine: null, verified: false },
  selects: [], plan: {}, attempts: [], preview_url: "", output: "", feedback: ""
};
require("fs").writeFileSync(process.argv[11], JSON.stringify(job, null, 2) + "\n");
' "${DATE}-${SLUG}" "$RAW" "$DUR" "$FPS" "$W" "$H" "$ROT" "$HAS_AUDIO" "$HDR" "$VCODEC" "$JOB/job.json"
fi

if [ "$HAS_AUDIO" = "1" ]; then NEXT="transcribe $JOB/audio16k.wav"; else NEXT="no audio: get a script or voiceover"; fi
echo "INGEST OK: $JOB  (proxy ${PDIM}, ${PDUR}s)  next: $NEXT"