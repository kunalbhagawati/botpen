#!/usr/bin/env bash
#
# lock.sh - mailbox client for coordinating agents.
#
# One shared file (mailbox.jsonl, next to this script) is the channel. Writes are
# serialized internally; the locking is an implementation detail you never touch.
#
# Commands:
#   send MSG [opts]     append a message (telemetry added automatically)
#   read [opts]         print messages (optionally filtered)
#   wait [opts]         block until a new matching message arrives, print it, exit
#
# send opts:  --session SID   sender id (default: $BOTS_SESSION, else cwd name, else host:pid)
#             --to SID        address the message to a specific session
#             --ref TS        mark as a reply to message with this ts
#             (MSG may also be piped on stdin instead of given as an argument)
#
# read opts:  --n N           only the last N matching messages
#             --from SID      only messages from this sender
#             --to SID        only messages addressed to this session
#             --since TS      only messages with ts greater than TS
#
# wait opts:  --session SID   your id (used to skip your own messages)
#             --from SID      only wake for messages from this sender
#             --to SID        only wake for messages addressed to this session
#             --timeout S     give up after S seconds (default: wait forever)
#             --poll S        poll interval in seconds (default 1)
#             --include-self  also wake for your own messages
#
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROG=$(basename "$0")

MAILBOX="$SCRIPT_DIR/mailbox.jsonl"
LOCKDIR="$SCRIPT_DIR/.mailbox.lock"
LOCK_TTL=10   # seconds; a lock older than this is assumed abandoned and reclaimed

usage() { sed -n '3,33p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

now_epoch() { date +%s; }
now_ts()    { date -u +%FT%TZ; }

mtime_epoch() {
  case "$(uname -s)" in
    Darwin | *BSD) stat -f %m "$1" 2>/dev/null || echo 0 ;;
    *) stat -c %Y "$1" 2>/dev/null || echo 0 ;;
  esac
}

# Resolve who "I" am for telemetry / self-skip.
resolve_session() {
  if [ -n "${1:-}" ]; then printf '%s' "$1"; return; fi
  if [ -n "${BOTS_SESSION:-}" ]; then printf '%s' "$BOTS_SESSION"; return; fi
  local base; base=$(basename "$PWD")
  if printf '%s' "$base" | grep -Eq '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'; then
    printf '%s' "$base"; return
  fi
  printf '%s:%s' "$(hostname 2>/dev/null || echo host)" "$$"
}

# --- internal mailbox lock (hidden). mkdir is atomic; stale locks self-heal. ---
_lock() {
  while ! mkdir "$LOCKDIR" 2>/dev/null; do
    local age=$(( $(now_epoch) - $(mtime_epoch "$LOCKDIR") ))
    if [ "$age" -ge "$LOCK_TTL" ]; then
      mv "$LOCKDIR" "$LOCKDIR.stale.$$" 2>/dev/null && rm -rf "$LOCKDIR.stale.$$"
      continue
    fi
    sleep 0.05
  done
}
_unlock() { rm -rf "$LOCKDIR"; }

cmd_send() {
  local msg="" session="" to="" ref="" have_msg=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --session) session="$2"; shift 2 ;;
      --to) to="$2"; shift 2 ;;
      --ref) ref="$2"; shift 2 ;;
      -h | --help) usage; exit 0 ;;
      -*) echo "$PROG: unknown option '$1'" >&2; exit 2 ;;
      *) msg="$1"; have_msg=1; shift ;;
    esac
  done
  if [ "$have_msg" -eq 0 ]; then
    msg=$(cat)   # read body from stdin
  fi
  session=$(resolve_session "$session")

  local line
  line=$(jq -nc --arg ts "$(now_ts)" --arg s "$session" --arg m "$msg" \
               --arg to "$to" --arg ref "$ref" '
    {ts:$ts, session:$s, msg:$m}
    + (if $to  != "" then {to:$to}   else {} end)
    + (if $ref != "" then {ref:$ref} else {} end)')

  _lock
  # shellcheck disable=SC2064
  trap "_unlock" EXIT INT TERM
  printf '%s\n' "$line" >> "$MAILBOX"
  _unlock
  trap - EXIT INT TERM
}

cmd_read() {
  local n="" from="" to="" since=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --n) n="$2"; shift 2 ;;
      --from) from="$2"; shift 2 ;;
      --to) to="$2"; shift 2 ;;
      --since) since="$2"; shift 2 ;;
      -h | --help) usage; exit 0 ;;
      *) echo "$PROG: unknown option '$1'" >&2; exit 2 ;;
    esac
  done
  [ -f "$MAILBOX" ] || return 0
  local out
  out=$(jq -c --arg from "$from" --arg to "$to" --arg since "$since" '
    select(($from=="" or .session==$from)
       and ($to=="" or .to==$to)
       and ($since=="" or .ts>$since))' "$MAILBOX")
  if [ -n "$n" ]; then
    printf '%s\n' "$out" | tail -n "$n"
  else
    printf '%s\n' "$out"
  fi
}

# Does one JSONL line pass the wait filter? prints it if yes.
_wait_match() {
  jq -c --arg self "$1" --arg from "$2" --arg to "$3" --argjson incself "$4" '
    select(($incself or .session!=$self)
       and ($from=="" or .session==$from)
       and ($to=="" or .to==$to))' 2>/dev/null
}

cmd_wait() {
  local session="" from="" to="" timeout="-1" poll="1" incself="false"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --session) session="$2"; shift 2 ;;
      --from) from="$2"; shift 2 ;;
      --to) to="$2"; shift 2 ;;
      --timeout) timeout="$2"; shift 2 ;;
      --poll) poll="$2"; shift 2 ;;
      --include-self) incself="true"; shift ;;
      -h | --help) usage; exit 0 ;;
      *) echo "$PROG: unknown option '$1'" >&2; exit 2 ;;
    esac
  done
  session=$(resolve_session "$session")

  local seen start
  seen=$([ -f "$MAILBOX" ] && wc -l < "$MAILBOX" | tr -d ' ' || echo 0)
  start=$(now_epoch)

  while true; do
    if [ -f "$MAILBOX" ]; then
      local total
      total=$(wc -l < "$MAILBOX" | tr -d ' ')
      if [ "$total" -gt "$seen" ]; then
        local hit=0
        while IFS= read -r line; do
          local m
          m=$(printf '%s\n' "$line" | _wait_match "$session" "$from" "$to" "$incself")
          if [ -n "$m" ]; then printf '%s\n' "$m"; hit=1; fi
        done < <(tail -n "+$((seen + 1))" "$MAILBOX")
        seen="$total"
        [ "$hit" -eq 1 ] && exit 0
      fi
    fi
    if [ "$timeout" -ge 0 ] && [ "$(( $(now_epoch) - start ))" -ge "$timeout" ]; then
      echo "$PROG: wait timed out after ${timeout}s" >&2
      exit 1
    fi
    sleep "$poll"
  done
}

main() {
  if [ "$#" -eq 0 ]; then usage; exit 2; fi
  local sub="$1"; shift
  case "$sub" in
    send) cmd_send "$@" ;;
    read) cmd_read "$@" ;;
    wait) cmd_wait "$@" ;;
    -h | --help | help) usage ;;
    *) echo "$PROG: unknown command '$sub'" >&2; usage; exit 2 ;;
  esac
}

main "$@"
