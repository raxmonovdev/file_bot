#!/bin/bash
# Botni ushlab turadi: yiqilsa qayta ko'taradi, noutbuk uyg'onsa qayta ulaydi.
set -u

ROOT="/Users/raxmonovichdev/File bot/pdf_mega_bot"
PY="$ROOT/.venv/bin/python"
WATCH_SRC="$ROOT/scripts/wake_watch.c"
WATCH_BIN="$ROOT/scripts/wake_watch"
PIDFILE="$ROOT/logs/bot.pid"
LOG="$ROOT/logs/service.log"

mkdir -p "$ROOT/logs"
cd "$ROOT" || exit 1

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG"
}

stop_bot() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi
}

cleanup() {
  stop_bot
  if [[ -n "${WATCH_PID:-}" ]]; then
    kill "$WATCH_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ ! -x "$WATCH_BIN" || "$WATCH_SRC" -nt "$WATCH_BIN" ]]; then
  if clang -framework IOKit -framework CoreFoundation -O2 -o "$WATCH_BIN" "$WATCH_SRC" >>"$LOG" 2>&1; then
    log "uyqu kuzatuvchisi tayyor"
  else
    log "uyqu kuzatuvchisi yig'ilmadi, faqat oddiy qayta ishga tushirish ishlaydi"
    WATCH_BIN=""
  fi
fi

if [[ -n "$WATCH_BIN" && -x "$WATCH_BIN" ]]; then
  "$WATCH_BIN" | while IFS= read -r event; do
    if [[ "$event" == "wake" ]]; then
      log "noutbuk uyg'ondi, tarmoq chiqishi uchun 8 soniya kutiladi"
      sleep 8
      if [[ -f "$PIDFILE" ]]; then
        kill "$(cat "$PIDFILE")" 2>/dev/null || true
      fi
    fi
  done &
  WATCH_PID=$!
fi

log "xizmat boshlandi"
while true; do
  if ! "$PY" -c 'from config import settings; raise SystemExit(0 if settings.bot_token else 1)' >/dev/null 2>&1; then
    log "BOT_TOKEN bo'sh, .env saqlanguncha kutiladi"
    sleep 15
    continue
  fi

  log "bot ishga tushmoqda"
  "$PY" -u main.py >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  started=$SECONDS
  wait "$(cat "$PIDFILE")"
  code=$?
  rm -f "$PIDFILE"
  ran=$((SECONDS - started))
  log "bot to'xtadi (kod $code, ${ran}s)"
  if (( ran < 8 )); then
    sleep 15
  else
    sleep 3
  fi
done
