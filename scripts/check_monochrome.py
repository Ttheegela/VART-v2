"""Fail on colour in the UI: colours, coloured emoji and colour filters.

Allowed: black, white, transparent, current, neutral-* and true greys.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = {".ts", ".tsx", ".css", ".svg", ".js", ".jsx", ".html"}  # what web/src can ship to a browser
PALETTES = (
    "red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
    "|slate|gray|zinc|stone|taupe|mauve|mist|olive"
)
# Every CSS named colour (148). transparent, currentcolor and inherit are keywords, not colour names, so they
# never match; black, white and the true greys are colour names that stay allowed.
CSS_COLOURS = """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown
    burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
    darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
    darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet
    deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro
    ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow
    lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray
    lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine
    mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise
    mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab
    orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru
    pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
    seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan
    teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen
""".split()  # noqa: SIM905
GREYS = """
    black white gray grey silver gainsboro whitesmoke dimgray dimgrey darkgray darkgrey lightgray lightgrey
""".split()  # noqa: SIM905
# CSS system colours that are not greys (LinkText is blue, Highlight and Mark are coloured in every browser).
SYSTEM = """
    linktext visitedtext activetext highlight highlighttext accentcolor accentcolortext mark marktext
    selecteditem selecteditemtext
""".split()  # noqa: SIM905
UTILITY = re.compile(rf"\b[a-z]+(?:-[a-z]+)*-(?:{PALETTES})-(?:50|[1-9]00|950)\b")
# #rgb, #rgba, #rrggbb and #rrggbbaa. Not a character reference (&#8212;), a fragment glued to a word
# (docs#add) or to url( (url(#bad)), and not the start of a longer name (#fade-in). An underscore may touch it
# on either side, because in a Tailwind arbitrary value it is a space:
# bg-[linear-gradient(to_right,#f00_0%,#00f_100%)].
HEX = re.compile(
    r"(?<![&A-Za-z0-9])(?<!url\()(?<!url\([\x22\x27])"
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9A-Za-z-])"
)
# CSS function names are case-insensitive: RGB( is rgb(.
FUNCTION = re.compile(r"(?<![\w-])(?:rgba?|hsla?|hwb|oklch|oklab|lab|lch|color-mix|color)\(", re.IGNORECASE)
# Emoji draw in colour whatever the CSS says: U+1F000-U+1FAFF, the check mark and cross emoji (U+2705, U+274C,
# U+274E), the star (U+2B50) and the emoji presentation selector (U+FE0F), which turns a text glyph into an
# emoji. The plain text glyphs U+2713 (check mark) and U+2717 (ballot x) are not emoji and stay allowed. The
# class is written as escapes, so this file stays ASCII.
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2705\u274C\u274E\u2B50\uFE0F]")
# Filters that tint a grey element: Tailwind sepia, hue-rotate-<n> and saturate-<n> from 100 up, and the CSS
# functions sepia( and hue-rotate( (function names are case-insensitive; Tailwind classes are not).
FILTER = re.compile(r"\b(?:sepia|hue-rotate-\d+|saturate-(?:[2-9]\d\d|1\d\d))\b|\b(?i:sepia|hue-rotate)\(")


# A colour name only styles something where it is a value, so prose such as "red-flagged" or "the green light"
# is left alone. It is matched whole: not inside a longer word, a hyphenated name, a path or a member access.
def _names(names: set[str]) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9./-])(?:{'|'.join(sorted(names))})(?![A-Za-z0-9.-])", re.IGNORECASE)


NAMED = _names((set(CSS_COLOURS) - set(GREYS)) | set(SYSTEM))
# In a script, mark, highlight and linkText are ordinary identifiers; a system colour counts only when quoted.
SCRIPT_NAMED = _names(set(CSS_COLOURS) - set(GREYS))
QUOTED = re.compile(r""""[^"]*"|'[^']*'|`[^`]*`""")
# Custom properties, anything ending in color or shadow (accent-color, borderTopColor, box-shadow, ...),
# filter (drop-shadow() takes a colour) and the colour shorthands.
_PROPERTY = (
    r"(?<![\w-])(?:--[\w-]+|[\w-]*(?:color|shadow)|filter"
    r"|(?:background|border|fill|stroke|outline|text-?decoration|text-?emphasis|caret|column-?rule"
    r"|-webkit-text-stroke)[\w-]*)"
)
# In a script a value ends at ; or }, at the comma before the next object key, or at the line's end (commas
# inside parentheses or a quoted string stay: boxShadow: "0 0 1px black, 0 0 2px red"). In a CSS file a
# declaration ends only at ; or } (or the { of a rule: .a:hover {), so commas and newlines are inside it.
_VALUE = r"""(?:"[^"\n]*"|'[^'\n]*'|[^;,}()\n]|\((?:[^()]|\([^()]*\))*\))*"""
_CSS_VALUE = r"(?:[^;{}()]|\((?:[^()]|\([^()]*\))*\))*"


def _style_values(value: str, unquoted: bool) -> tuple[re.Pattern[str], ...]:
    attribute = r""""[^"]*"|'[^']*'|\{[^{}]*\}""" + (r"""|[^\s>"'{}]+""" if unquoted else "")
    return (
        # color: red;  { backgroundColor: "red" }   (CSS declarations and JS/TS style objects)
        re.compile(_PROPERTY + r"""["']?\s*:\s*(?P<value>""" + value + ")", re.IGNORECASE),
        # fill="red"  stroke={dark ? "red" : "black"}  and, in HTML and SVG only, fill=red   (attributes; in a
        # script `border = x` is an assignment)
        re.compile(_PROPERTY + r"\s*=\s*(?P<value>" + attribute + ")", re.IGNORECASE),
        # bg-[red]  shadow-[0_0_4px_red]   (Tailwind arbitrary values)
        re.compile(r"-\[(?P<value>[^\]]*)\]"),
    )


STYLE_VALUES = _style_values(_VALUE, unquoted=False)
MARKUP_STYLE_VALUES = _style_values(_VALUE, unquoted=True)
CSS_STYLE_VALUES = _style_values(_CSS_VALUE, unquoted=False)
MARKUP = {".html", ".svg"}


def _grey(hex_colour: str) -> bool:
    h = hex_colour[1:]
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    return h[0:2].lower() == h[2:4].lower() == h[4:6].lower()  # red, green, blue; any alpha is ignored


def _colour_names(text: str, patterns: tuple[re.Pattern[str], ...], script: bool) -> list[tuple[int, str]]:
    """(line, name) for each colour name in a style value; the whole text is scanned, so a declaration may
    span lines. By position, so a name two patterns both see (bg-[color:red]) counts once."""
    hits: dict[int, tuple[int, str]] = {}
    for pattern in patterns:
        for style in pattern.finditer(text):
            line = text.count("\n", 0, style.start()) + 1
            at, value = style.start("value"), style["value"]
            names = [
                (at + m.start(), m.group(0)) for m in (SCRIPT_NAMED if script else NAMED).finditer(value)
            ]
            if script:  # a system colour only inside a string
                names += [
                    (at + q.start() + m.start(), m.group(0))
                    for q in QUOTED.finditer(value)
                    for m in NAMED.finditer(q.group(0))
                ]
            for pos, name in names:
                hits[pos] = (line, name)
    return list(hits.values())


def violations(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    css, markup = path.suffix == ".css", path.suffix in MARKUP
    patterns = CSS_STYLE_VALUES if css else MARKUP_STYLE_VALUES if markup else STYLE_VALUES
    names = _colour_names(text, patterns, script=not (css or markup))
    found = [f"{path}:{n}: colour name {name}" for n, name in names]
    for n, line in enumerate(text.splitlines(), start=1):
        found += [f"{path}:{n}: colour utility {m.group(0)}" for m in UTILITY.finditer(line)]
        found += [
            f"{path}:{n}: non-grey colour {m.group(0)}" for m in HEX.finditer(line) if not _grey(m.group(0))
        ]
        found += [f"{path}:{n}: colour function {m.group(0)}" for m in FUNCTION.finditer(line)]
        found += [f"{path}:{n}: coloured emoji U+{ord(m.group(0)):04X}" for m in EMOJI.finditer(line)]
        found += [f"{path}:{n}: colour filter {m.group(0)}" for m in FILTER.finditer(line)]
    return found


def main() -> int:
    files = [p for p in (ROOT / "web" / "src").rglob("*") if p.suffix in SUFFIXES]
    files += (ROOT / "web" / "public").rglob("*.svg")  # served as they are: every icon and logo
    files.append(ROOT / "web" / "index.html")
    files = [f for f in files if f.exists() and f.name != "api-types.ts"]  # api-types.ts is generated
    problems = [v for f in files for v in violations(f)]
    for p in problems:
        print(p, file=sys.stderr)
    if not files:  # a wrong ROOT or a moved web/ must not read as a clean UI
        print("monochrome: no files to check under web/ (src, index.html, public/*.svg)", file=sys.stderr)
        return 1
    print(f"monochrome: {len(files)} files checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
