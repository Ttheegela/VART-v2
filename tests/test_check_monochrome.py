from pathlib import Path

import pytest

from scripts import check_monochrome
from scripts.check_monochrome import CSS_COLOURS, violations

SHADES = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")
TAILWIND_PALETTES = """
    red orange amber yellow lime green emerald teal cyan sky blue indigo violet purple fuchsia pink rose
    slate gray zinc stone taupe mauve mist olive
""".split()  # noqa: SIM905


def _file(tmp_path: Path, text: str, name: str = "a.tsx") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_colour_utilities_are_flagged(tmp_path: Path) -> None:
    found = violations(_file(tmp_path, '<div className="bg-blue-500 text-red-600 hover:border-emerald-300">'))
    assert len(found) == 3


def test_neutral_black_and_white_are_allowed(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, '<p className="bg-neutral-100 text-black border-white">')) == []


def test_tinted_greys_are_flagged_to_keep_one_grey_family(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, '<p className="text-slate-700 bg-zinc-50">'))


def test_hex_colours_must_be_grey(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, ".a { color: #ff0000 }", "a.css"))
    assert violations(_file(tmp_path, ".a { color: #333; background: #f5f5f5 }", "a.css")) == []


def test_colour_functions_are_flagged(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, ".a { color: rgb(10 20 30) }", "a.css"))


# Every Tailwind palette and every shade is a colour utility; neutral is the one grey family that is allowed.


@pytest.mark.parametrize("palette", TAILWIND_PALETTES)
def test_every_tailwind_palette_is_flagged(tmp_path: Path, palette: str) -> None:
    assert len(violations(_file(tmp_path, f'<p className="bg-{palette}-500">'))) == 1


@pytest.mark.parametrize("shade", SHADES)
def test_every_shade_is_flagged(tmp_path: Path, shade: str) -> None:
    assert len(violations(_file(tmp_path, f'<p className="text-red-{shade}">'))) == 1


def test_neutral_is_allowed_at_every_shade(tmp_path: Path) -> None:
    classes = " ".join(f"bg-neutral-{shade}" for shade in SHADES)
    assert violations(_file(tmp_path, f'<p className="{classes}">')) == []


# Ruling 24 (a): 4- and 8-digit hex. Only the red, green and blue channels decide; alpha is ignored.


def test_four_and_eight_digit_hex_must_be_grey(tmp_path: Path) -> None:
    found = violations(_file(tmp_path, ".a { color: #f00f; background: #ff000080 }", "a.css"))
    assert len(found) == 2


def test_alpha_does_not_make_a_grey_hex_colourful(tmp_path: Path) -> None:
    css = ".a { color: #0000; background: #00000080; border-color: #ffff; fill: #333a }"
    assert violations(_file(tmp_path, css, "a.css")) == []


def test_numeric_character_references_are_not_hex_colours(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, "<p>Loading&#8230; done &#8212; &#169;</p>")) == []


# In a Tailwind arbitrary value an underscore is a space, so a hex colour can sit between underscores.


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ('<div className="bg-[linear-gradient(to_right,#f00_0%,#00f_100%)]">', 2),
        ('<div className="shadow-[#f00_0_0_4px]">', 1),
        ('<div className="border-[1px_solid_#f00]">', 1),
    ],
)
def test_hex_colours_in_tailwind_arbitrary_values_are_flagged(tmp_path: Path, text: str, count: int) -> None:
    found = violations(_file(tmp_path, text))
    assert len(found) == count
    assert all("non-grey colour" in v for v in found)


def test_hash_text_that_is_not_a_colour_is_left_alone(tmp_path: Path) -> None:
    text = "\n".join(
        [
            "#fade-in { animation: none }",  # an id selector that starts like a hex colour
            '<circle fill="url(#bad)" />',  # a fragment reference
            "<circle fill=\"url('#bad')\" />",
            '<a href="/docs#add">docs</a>',  # a fragment glued to a word
        ]
    )
    assert violations(_file(tmp_path, text)) == []


# Ruling 24 (b): CSS named colours, but only where they style something.


@pytest.mark.parametrize(
    ("text", "filename", "count"),
    [
        # CSS property values
        (".a { color: red }", "a.css", 1),
        (".a { background: Tomato; }", "a.css", 1),
        (".a { border: 1px solid blue }", "a.css", 1),
        (".a { outline-color: orange; text-decoration: underline crimson }", "a.css", 2),
        (".a { background: linear-gradient(to right, black, teal) }", "a.css", 1),
        (":root { --accent: rebeccapurple }", "a.css", 1),
        # every property the rule names, plain and as -color variants
        (
            ".a { caret: red; column-rule: 1px solid green; stroke: orange; fill: pink; outline: violet }",
            "a.css",
            5,
        ),
        (".a { caret-color: red; accent-color: blue; column-rule-color: green }", "a.css", 3),
        (".a { text-decoration-color: pink; background-color: gold; border-top-color: tan }", "a.css", 3),
        (".a { border-left: 1px solid navy; text-decoration: underline wavy lime }", "a.css", 2),
        # shadows and filters carry colours too
        (".a { box-shadow: 0 0 4px red }", "a.css", 1),
        (".a { text-shadow: 1px 1px green; filter: drop-shadow(0 0 2px pink) }", "a.css", 2),
        # JS/TS style objects
        ('<p style={{ color: "red" }}>x</p>', "a.tsx", 1),
        ("const s = { backgroundColor: 'blue', borderTopColor: \"green\" };", "a.ts", 2),
        ('const s = { fill: dark ? "white" : "pink" };', "a.ts", 1),
        ('const s = { caretColor: "red", textDecoration: "wavy pink", columnRule: "teal" };', "a.ts", 3),
        ('const s = { boxShadow: "0 0 4px red", filter: "drop-shadow(0 0 2px green)" };', "a.ts", 2),
        # HTML, SVG and JSX attributes
        ('<path fill="red" stroke="#000" />', "a.svg", 1),
        ('<Icon stroke={error ? "red" : "black"} />', "a.tsx", 1),
        # Tailwind arbitrary values (bg-[color:green] is seen by two patterns and counts once)
        ('<div className="bg-[red] text-[blue]">', "a.tsx", 2),
        ('<div className="shadow-[0_0_4px_red] bg-[color:green]">', "a.tsx", 2),
    ],
)
def test_colour_names_are_flagged_where_they_style(
    tmp_path: Path, text: str, filename: str, count: int
) -> None:
    found = violations(_file(tmp_path, text, filename))
    assert len(found) == count
    assert all("colour name" in v for v in found)


@pytest.mark.parametrize(
    "name",
    [
        "black",
        "white",
        "transparent",
        "currentColor",
        "currentcolor",
        "inherit",
        "gray",
        "grey",
        "silver",
        "gainsboro",
        "whitesmoke",
        "dimgray",
        "dimgrey",
        "darkgray",
        "darkgrey",
        "lightgray",
        "lightgrey",
    ],
)
def test_black_white_transparent_current_and_true_greys_are_allowed_names(tmp_path: Path, name: str) -> None:
    css = f".a {{ color: {name}; background: {name.upper()}; border: 1px solid {name} }}"
    assert violations(_file(tmp_path, css, "a.css")) == []


def test_allowed_names_pass_in_attributes_style_objects_and_tailwind(tmp_path: Path) -> None:
    ui = (
        '<path fill="white" stroke={"black"} className="bg-[silver] text-[transparent]" '
        'style={{ color: "DimGray" }} />'
    )
    assert violations(_file(tmp_path, ui)) == []


def test_shadows_and_filters_in_greys_are_allowed(tmp_path: Path) -> None:
    text = "\n".join(
        [
            ".a { box-shadow: 0 1px 2px #0003; filter: blur(2px) drop-shadow(0 0 2px black) }",
            # only the filter property itself holds a colour, not every name that starts with it
            'const filterLabel = "Red flags";',
        ]
    )
    assert violations(_file(tmp_path, text)) == []


def test_the_named_colour_table_holds_all_148_css_colours() -> None:
    assert len(CSS_COLOURS) == len(set(CSS_COLOURS)) == 148


@pytest.mark.parametrize(
    "name",
    [
        "chartreuse",
        "peachpuff",
        "lightgoldenrodyellow",
        "rebeccapurple",
        "slategray",
        "slategrey",
        "lightslategray",
        "lightslategrey",
        "darkslategray",
        "darkslategrey",
    ],
)
def test_long_names_and_tinted_greys_are_flagged(tmp_path: Path, name: str) -> None:
    assert len(violations(_file(tmp_path, f".a {{ color: {name} }}", "a.css"))) == 1


def test_colour_words_in_ui_copy_are_not_colours(tmp_path: Path) -> None:
    copy = "\n".join(
        [
            "<p>Ordered items stay red-flagged until the green light.</p>",
            'const note = "Orange is the new red-flagged"; // blue sky',
            'const row = { title: "Green light", label: "Red flag" };',
            # a style key's value ends at the comma: the next key's text is not a colour
            '{ border: "1px solid #000", note: "Red alert" }',
            # ... at the closing brace of a style object, and at the semicolon of a style attribute
            '<p style={{ color: "#333" }}>Red flag</p>',
            '<p style="color: #333;">Green light</p>',
            # paths and variable names that contain a colour word are not colours
            ".a { background: url(/img/red.png) var(--red); color: var(--green) }",
            ".a { background: url(red-hero.png) } .b { fill: url(green.svg) }",
        ]
    )
    assert violations(_file(tmp_path, copy)) == []


# Ruling 24 (c): color-mix(, hwb( and color(, which must not be the end of a longer name.


@pytest.mark.parametrize(
    "text",
    [
        ".a { background: color-mix(in srgb, black 40%, white) }",
        ".a { color: hwb(0 0% 0%) }",
        ".a { color: color(display-p3 1 0 0) }",
        '<div className="bg-[color(display-p3_1_0_0)]">',
    ],
)
def test_more_colour_functions_are_flagged(tmp_path: Path, text: str) -> None:
    found = violations(_file(tmp_path, text))
    assert len(found) == 1
    assert "colour function" in found[0]


@pytest.mark.parametrize(
    "function",
    ["rgb", "rgba", "hsl", "hsla", "oklch", "oklab", "lab", "lch", "hwb", "color-mix", "color"],
)
def test_every_colour_function_is_flagged_in_any_case(tmp_path: Path, function: str) -> None:
    # CSS function names are case-insensitive: rgb(), RGB() and Rgb() are the same function.
    for spelling in (function, function.upper(), function.title()):
        found = violations(_file(tmp_path, f".a {{ background: {spelling}(1 2 3) }}", "a.css"))
        assert len(found) == 1, spelling
        assert "colour function" in found[0]


def test_colour_function_names_must_stand_alone(tmp_path: Path) -> None:
    code = "get_color(x); bg-color(y); mycolor(z); setColor(a); getBackgroundColor(b); const c = pick(color);"
    assert violations(_file(tmp_path, code)) == []


# main() walks web/src, web/index.html and web/public/favicon.svg under check_monochrome.ROOT.


def _tree(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def test_main_passes_a_clean_tree_and_counts_only_the_files_it_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _tree(
        tmp_path,
        {
            "web/src/App.tsx": '<p className="text-black">x</p>\n',
            "web/src/index.css": '@import "tailwindcss";\n',
            "web/index.html": "<html></html>\n",
            # generated from the OpenAPI schema: skipped, so not counted either
            "web/src/lib/api-types.ts": 'export const x = "bg-red-500";\n',
        },
    )
    monkeypatch.setattr(check_monochrome, "ROOT", tmp_path)
    assert check_monochrome.main() == 0
    # there is no favicon.svg in this tree, so it is not counted
    assert capsys.readouterr().out.strip() == "monochrome: 3 files checked, 0 problems"


@pytest.mark.parametrize(
    "path",
    ["web/src/App.tsx", "web/src/util.ts", "web/src/index.css", "web/index.html", "web/public/favicon.svg"],
)
def test_main_fails_on_a_colour_in_any_scanned_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], path: str
) -> None:
    _tree(tmp_path, {path: 'ok\n<p className="bg-red-500">x</p>\n'})
    monkeypatch.setattr(check_monochrome, "ROOT", tmp_path)
    assert check_monochrome.main() == 1
    captured = capsys.readouterr()
    assert f"{tmp_path / path}:2: colour utility bg-red-500" in captured.err
    assert "1 problems" in captured.out


def test_main_fails_when_there_is_nothing_to_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check_monochrome, "ROOT", tmp_path)  # no web/ in here
    assert check_monochrome.main() == 1
    assert "no files" in capsys.readouterr().err
