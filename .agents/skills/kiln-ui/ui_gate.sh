#!/bin/bash
# kiln-ui gate: flags custom CSS and non-house controls in web UI changes.
#
# Usage:
#   ui_gate.sh --range <git-range> [--repo <path>]   # added lines of a diff (the unit's landing check)
#   ui_gate.sh --files <file>...                       # whole .svelte files (calibration, audits)
#   ui_gate.sh --worktree [--repo <path>]              # added lines of the uncommitted diff, plus untracked files
#
# Output: one line per hit  SEV<TAB>RULE<TAB>file:line<TAB>snippet, then a summary.
# SEV: FAIL = the unit does not land unless the component plan justifies the hit by
#      file:line; WARN = must appear as a row in the component plan; INFO = listed only.
# Exit 1 when any FAIL hit remains. Allowlist: ui_gate_allow.txt beside this script (one regex per
# line, matched against "file<TAB>snippet", optionally prefixed "RULE_NAME:" to scope it to that one
# rule), for house idioms that are not defects.
#
# Rules are tuned on the eval builder route and calibrated on the rest of app/web_ui/src/routes
# (43k lines): the reference screens (run page, edit task, synthetic data) run at 0 FAIL.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ALLOW="$HERE/ui_gate_allow.txt"
REPO=.
MODE=""; RANGE=""; FILES=()
while [ $# -gt 0 ]; do
  case "$1" in
    --range) MODE=range; RANGE=$2; shift 2;;
    --worktree) MODE=worktree; shift;;
    --files) MODE=files; shift; while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do FILES+=("$1"); shift; done;;
    --repo) REPO=$2; shift 2;;
    *) echo "unknown arg $1" >&2; exit 2;;
  esac
done
[ -z "$MODE" ] && { sed -n 2,17p "$0"; exit 2; }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
LINES="$TMP/lines.tsv"   # file:line<TAB>content

# ---- collect the lines under review -------------------------------------------------------
svelte_only() { grep -E '^app/web_ui/src/.*\.svelte:' | grep -vE '\.test\.|/__tests__/|_mock|/dev/|/preview/'; }
# Untracked files are invisible to `git diff`, so a brand-new component would otherwise review as
# zero lines. Worktree mode scans each of them whole, the way --files does.
untracked_files() { git -C "$REPO" ls-files --others --exclude-standard -- 'app/web_ui/src'; }
case "$MODE" in
  files)
    for f in "${FILES[@]}"; do
      case "$f" in *.test.*|*/__tests__/*) continue;; esac
      # Only markup is reviewable: a guide or a script carries <label> examples that are not screens.
      case "$f" in *.svelte) ;; *) echo "skipped, not a .svelte file: $f" >&2; continue;; esac
      awk -v f="$f" '{ print f ":" NR "\t" $0 }' "$f"
    done > "$LINES" ;;
  range|worktree)
    if [ "$MODE" = range ]; then D=(git -C "$REPO" diff -U0 "$RANGE"); else D=(git -C "$REPO" diff -U0 HEAD); fi
    "${D[@]}" -- 'app/web_ui/src' | awk '
      /^diff --git/ { file=$4; sub(/^b\//,"",file); next }
      /^@@/ { split($3,a,","); ln=substr(a[1],2)+0; next }
      /^\+\+\+/ { next }
      /^\+/ { print file ":" ln "\t" substr($0,2); ln++; next }
      /^-/ { next }
      { ln++ }' | svelte_only > "$LINES"
    if [ "$MODE" = worktree ]; then
      untracked_files | grep -E '\.svelte$' | grep -vE '\.test\.|/__tests__/|_mock|/dev/|/preview/' \
        | while read -r f; do awk -v f="$f" '{ print f ":" NR "\t" $0 }' "$REPO/$f"; done >> "$LINES"
    fi
    # shared controls touched: any file in the diff under the shared dirs (lib/ui, lib/components, the form
    # controls, app_page, and the SDG kiln_pro_* components the builder shares), added OR removed lines
    { "${D[@]}" --name-only -- 'app/web_ui/src'; [ "$MODE" = worktree ] && untracked_files; } \
      | grep -E '^app/web_ui/src/(lib/ui/|lib/components/|lib/utils/form_|routes/\(app\)/app_page\.svelte|routes/\(app\)/generate/\[project_id\]/\[task_id\]/kiln_pro_)' \
      | grep -vE '\.test\.|/__tests__/' | sed 's/^/FAIL\tSHARED_CONTROL_TOUCHED\t/; s/$/:0\tshared control edited: must be a separate named decision in the brief/' > "$TMP/shared.tsv" ;;
esac
[ -f "$TMP/shared.tsv" ] || : > "$TMP/shared.tsv"

# Comment text is not markup. Comment SPANS (<!-- -->, /* */, on one line or across several) are
# cut out of each reviewed line by scanning the whole file at the reviewed revision, so prose that
# mentions "btn-outline" is not a hit while markup before or after the comment on the same line
# still is. Single-line markers (// and --) are dropped by prefix.
CODE="$TMP/code.tsv"
code_spans() {  # <file> -> prints "file:line<TAB>the line with every comment span removed"
  local f=$1 src
  case "$MODE" in
    range) src=$(git -C "$REPO" show "${RANGE##*..}:$f" 2>/dev/null) ;;
    *)     src=$(cat "$([ "$MODE" = files ] && echo "$f" || echo "$REPO/$f")" 2>/dev/null) ;;
  esac
  [ -z "$src" ] && return 0
  printf '%s\n' "$src" | awk -v f="$f" '
    { rest=$0; out=""
      while (1) {
        if (!inblk) { o1=index(rest,"<!--"); o2=index(rest,"/*"); o=(o1&&o2)?(o1<o2?o1:o2):(o1?o1:o2)
                      if (!o) { out=out rest; break }
                      inblk=(o==o1)?1:2; out=out substr(rest,1,o-1); rest=substr(rest,o+ (inblk==1?4:2)) }
        else { c=index(rest,(inblk==1)?"-->":"*/"); if (!c) { rest=""; break }
               rest=substr(rest,c+ ((inblk==1)?3:2)); inblk=0 }
      }
      print f ":" NR "\t" out
    }'
}
cut -d: -f1 "$LINES" | sort -u | while read -r f; do code_spans "$f"; done > "$TMP/spans.tsv"
# Replace each reviewed line with its comment-free text; a line that is all comment drops out.
awk -F'\t' 'NR==FNR { c=$0; sub(/^[^\t]*\t/,"",c); span[$1]=c; seen[$1]=1; next }
     { c=$0; sub(/^[^\t]*\t/,"",c); if (seen[$1]) c=span[$1]
       if (c ~ /^[[:space:]]*$/) next
       print $1 "\t" c }' "$TMP/spans.tsv" "$LINES" \
  | grep -vE $'\t[[:space:]]*(//|\\*|--)' > "$CODE" || true

# ---- rules --------------------------------------------------------------------------------
# R <sev> <rule> <grep -E pattern> [exclude pattern]
R() {
  local sev=$1 rule=$2 pat=$3 excl=${4:-'^$'}
  grep -E "$pat" "$CODE" | grep -vE "$excl" | { if [ -n "${5:-}" ]; then grep -E "$5"; else cat; fi; } | { if [ -n "${6:-}" ]; then grep -E "$6"; else cat; fi; } | sed "s/^/$sev\t$rule\t/"
}
{
cat "$TMP/shared.tsv"
# 1. A form field built by hand instead of FormElement (checkbox/radio/file/hidden and the
#    drawer toggle are not form fields in the guide's sense).
R FAIL RAW_FORM_FIELD '<(textarea|input|select)\b' 'type="(checkbox|radio|file|hidden|search)"|drawer-toggle|class="(toggle|range|rating|checkbox)|rating-hidden|placeholder="Search'
# 2. A hand-written <label> (FormElement owns labels). Drawer labels and daisy label wrappers excluded.
R FAIL RAW_LABEL '<label\b' 'for="main-drawer"|drawer-|class="label\b|class="cursor-pointer label'
# 3. A hand-rolled expander (Collapse owns disclosure).
R FAIL HANDROLLED_EXPANDER 'aria-expanded=|rotate-180|expanded[[:space:]]*=[[:space:]]*!' 'lib/ui/collapse\.svelte|dropdown|menu'
# 4. Selection state painted with a status colour (the house selection style is
#    btn-outline -> btn-secondary when selected; see routes/(app)/run/rating.svelte).
R FAIL STATUS_COLOR_TOGGLE "\\?[[:space:]]*['\"]btn-(success|error|warning)['\"]|btn-(success|error|warning)['\"][[:space:]]*:[[:space:]]*['\"]btn-outline"
# 5. "View ..." as a button label.
R FAIL VIEW_LABEL '(<button[^>]*>|label:[[:space:]]*"|>)[[:space:]]*View [A-Z]|^[^	]+	[[:space:]]*View [A-Z][A-Za-z]*( [A-Za-z]+)*[[:space:]]*$' '<summary|<a\b|href='
# 6. A self-styled rounded container (rounded + surface/border + padding on one element)
#    that is not the documented card string. Badges, marks, avatars, pills excluded.
R FAIL TINTED_BOX 'class="[^"]*\brounded(-(sm|md|lg|xl|2xl|3xl))?\b[^"]*"' 'card card-bordered border-base-300 shadow-md|badge|<mark|rounded-full|avatar|loading|tooltip|dropdown|menu|modal|toast|progress|kbd|<input|<textarea|<code|<pre|overflow-x-auto|rounded-box' '\b(bg-(base-[0-9]+|primary|warning|success|error|info|gray|red|yellow|green|blue)(/[0-9]+)?|border-(warning|success|error|info|primary)/[0-9]+)\b' '\bp[xy]?-[0-9]'
R WARN ROUNDED_FRAME 'class="[^"]*\brounded(-(sm|md|lg|xl|2xl|3xl))?\b[^"]*\bborder\b[^"]*"' 'card card-bordered border-base-300 shadow-md|badge|<mark|rounded-full|avatar|loading|tooltip|dropdown|menu|modal|toast|progress|kbd|<input|<textarea|<code|<pre|bg-|border-(warning|success|error|info|primary)/'
# 7. A prop that overrides a shared control's typography or size.
R FAIL CONTROL_TYPOGRAPHY_OVERRIDE '\b(text_size|filled_icon)=' 'text_size="(sm|base)"'
# 8. Shadow or border colour added by hand outside the documented card string.
R WARN CUSTOM_SURFACE '\bshadow(-(sm|md|lg|xl))?\b|\bborder-(gray|slate|zinc|neutral|primary|secondary|success|error|warning|base-[0-9]+)(/[0-9]+)?\b' 'card card-bordered border-base-300 shadow-md|dropdown|menu|tooltip|<mark'
# 9. Ghost and outline buttons (house: standard grey btn; outline for special cases;
#    btn-outline btn-primary for pick-one-of-many).
R WARN GHOST_OR_OUTLINE_BUTTON '\bbtn-ghost\b|\bbtn-outline\b' 'btn-outline btn-primary|btn-primary btn-outline|btn-circle|btn-square'
# 10. Font weight outside the guide (bold only on page/section headings; semibold never).
R WARN FONT_WEIGHT '\bfont-(semibold|extrabold|black)\b|\bfont-bold\b' 'text-(xl|2xl|3xl) font-bold|font-bold text-(xl|2xl|3xl)'
# 11. Text colour outside the guide (text-gray-500 is the secondary colour).
R WARN NON_GUIDE_TEXT_COLOR '\btext-(gray|slate|zinc|neutral)-(300|400|600|700|800|900)\b' 'text-gray-400.*icon|<svg|placeholder'
# 12. Tinted backgrounds outside the palette section.
R WARN NON_GUIDE_BG '\bbg-(gray|slate|zinc|neutral|yellow|amber|red|green|blue)-[0-9]+\b|\bbg-(primary|secondary|success|error|warning|info)/[0-9]+\b' '<mark|MARK_CLASS'
# 13. Arbitrary values (house idioms allowlisted below).
R INFO ARBITRARY_VALUE '\[[0-9.]+(px|rem|vh|vw|%)\]|\[min\(|\[calc\(' 'max-w-\[(1400|900|300|340)px\]|min-h-\[50vh\]|max-h-\[(70|80)vh\]|min-h-\[calc\(100vh|w-\[70%\]|max-w-\[70%\]'
# An allow line prefixed "RULE_NAME:" only silences that rule; a bare line silences every rule.
} | { if [ -f "$ALLOW" ]; then grep -vE -f <(grep -vE '^\s*(#|$)' "$ALLOW" \
        | awk -v t="\t" '/^[A-Z_]+:/ { r=$0; sub(/:.*/,"",r); p=$0; sub(/^[A-Z_]+:/,"",p); print t r t ".*" p; next }
                          { print t "[A-Z_]+" t ".*" $0 }'); else cat; fi; } \
  | sort -t$'\t' -k1,1 -k2,2 -k3,3 | uniq > "$TMP/hits.tsv"

cat "$TMP/hits.tsv"
echo "=== kiln-ui gate: $(wc -l < "$LINES" | tr -d ' ') lines reviewed, $(wc -l < "$TMP/hits.tsv" | tr -d ' ') hits ==="
cut -f1,2 "$TMP/hits.tsv" | sort | uniq -c | sort -k2,2 -k1,1rn
NFAIL=$(grep -c '^FAIL' "$TMP/hits.tsv" || true)
if [ "${NFAIL:-0}" -gt 0 ]; then echo "RESULT: FAIL ($NFAIL FAIL hits: justify each by file:line in the component plan, or fix)"; exit 1; fi
echo "RESULT: PASS (WARN/INFO hits must appear as rows in the component plan)"
