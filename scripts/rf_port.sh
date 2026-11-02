# Used by the start buttons. Finds Reel Factory's own address so it never shares one with another app
# (Content Workshop uses 8765). Sets RF_PORT and URL, and remembers the choice in ~/.reelfactory/port.
mkdir -p "$HOME/.reelfactory"
PORT_FILE="$HOME/.reelfactory/port"
is_rf()   { curl -s --max-time 2 "http://127.0.0.1:$1/api/reels" 2>/dev/null | grep -q '"busy"'; }   # only Reel Factory answers this
is_free() { ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1 && ! curl -s --max-time 1 -o /dev/null "http://127.0.0.1:$1/" 2>/dev/null; }
START="$(cat "$PORT_FILE" 2>/dev/null)"; case "$START" in ''|*[!0-9]*|8765) START=8790;; esac
RF_PORT=""
for q in $(seq "$START" $((START + 30))) $(seq 8790 8820); do
  [ "$q" = 8765 ] && continue
  if is_rf "$q" || is_free "$q"; then RF_PORT=$q; break; fi
done
[ -z "$RF_PORT" ] && RF_PORT=8790
echo "$RF_PORT" > "$PORT_FILE"
export RF_DASH_PORT="$RF_PORT"
URL="http://127.0.0.1:$RF_PORT"
NAMED="http://reelfactory.localhost:$RF_PORT"
open_browser() { open -a "Google Chrome" "$NAMED/" 2>/dev/null || open "$URL/"; }
show_links() {
  echo ""
  echo "=============================================="
  echo "  Reel Factory is open in your browser."
  echo "  Make a reel:  $NAMED"
  echo "  Control:      $NAMED/index.html"
  echo "  (backup link: $URL)"
  echo "  (Hold Cmd and click a link to open it)"
  echo "=============================================="
}
