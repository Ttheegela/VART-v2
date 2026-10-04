"""Fail on colour in the UI. Allowed: black, white, transparent, current, neutral-* and true greys."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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

# A colour name only styles something where it is a value, so prose such as "red-flagged" or "the green light"
# is left alone. It is matched whole: not inside a longer word, a hyphenated name, a path or a member access.
_COLOURED = "|".join(sorted(set(CSS_COLOURS) - set(GREYS)))
NAMED = re.compile(rf"(?<![A-Za-z0-9./-])(?:{_COLOURED})(?![A-Za-z0-9.-])", re.IGNORECASE)
# Custom properties, anything ending in color or shadow (accent-color, borderTopColor, box-shadow, ...),
# filter (drop-shadow() takes a colour) and the colour shorthands.
_PROPERTY = (
    r"(?<![\w-])(?:--[\w-]+|[\w-]*(?:color|shadow)|filter"
    r"|(?:background|border|fill|stroke|outline|text-?decoration|caret|column-?rule)[\w-]*)"
)
# A value ends at ; or }, or at the comma before the next object key (commas inside parentheses stay).
_VALUE = r"(?:[^;,}()\n]|\((?:[^()]|\([^()]*\))*\))*"
STYLE_VALUES = (
    # color: red;  { backgroundColor: "red" }   (CSS declarations and JS/TS style objects)
    re.compile(_PROPERTY + r"""["']?\s*:\s*(?P<value>""" + _VALUE + ")", re.IGNORECASE),
    # fill="red"  stroke={dark ? "red" : "black"}   (HTML, SVG and JSX attributes)
    re.compile(_PROPERTY + r"""\s*=\s*(?P<value>"[^"]*"|'[^']*'|\{[^{}]*\})""", re.IGNORECASE),
    # bg-[red]  shadow-[0_0_4px_red]   (Tailwind arbitrary values)
    re.compile(r"-\[(?P<value>[^\]]*)\]"),
)


def _grey(hex_colour: str) -> bool:
    h = hex_colour[1:]
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    return h[0:2].lower() == h[2:4].lower() == h[4:6].lower()  # red, green, blue; any alpha is ignored


def _colour_names(line: str) -> list[str]:
    hits: dict[int, str] = {}  # by position, so a name two patterns both see (bg-[color:red]) counts once
    for pattern in STYLE_VALUES:
        for style in pattern.finditer(line):
            for name in NAMED.finditer(style["value"]):
                hits[style.start("value") + name.start()] = name.group(0)
    return list(hits.values())


def violations(path: Path) -> list[str]:
    found = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        found += [f"{path}:{n}: colour utility {m.group(0)}" for m in UTILITY.finditer(line)]
        found += [
            f"{path}:{n}: non-grey colour {m.group(0)}" for m in HEX.finditer(line) if not _grey(m.group(0))
        ]
        found += [f"{path}:{n}: colour name {name}" for name in _colour_names(line)]
        found += [f"{path}:{n}: colour function {m.group(0)}" for m in FUNCTION.finditer(line)]
    return found


def main() -> int:
    files = [p for p in (ROOT / "web" / "src").rglob("*") if p.suffix in {".ts", ".tsx", ".css"}]
    files += [ROOT / "web" / "index.html", ROOT / "web" / "public" / "favicon.svg"]
    files = [f for f in files if f.exists() and f.name != "api-types.ts"]  # api-types.ts is generated
    problems = [v for f in files for v in violations(f)]
    for p in problems:
        print(p, file=sys.stderr)
    if not files:  # a wrong ROOT or a moved web/ must not read as a clean UI
        print(
            "monochrome: no files to check under web/ (src, index.html, public/favicon.svg)", file=sys.stderr
        )
        return 1
    print(f"monochrome: {len(files)} files checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
