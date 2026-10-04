from pathlib import Path

import pytest

from scripts.check_monochrome import violations


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


# Ruling 24 (a): 4- and 8-digit hex. Only the red, green and blue channels decide; alpha is ignored.


def test_four_and_eight_digit_hex_must_be_grey(tmp_path: Path) -> None:
    found = violations(_file(tmp_path, ".a { color: #f00f; background: #ff000080 }", "a.css"))
    assert len(found) == 2


def test_alpha_does_not_make_a_grey_hex_colourful(tmp_path: Path) -> None:
    css = ".a { color: #0000; background: #00000080; border-color: #ffff; fill: #333a }"
    assert violations(_file(tmp_path, css, "a.css")) == []


def test_numeric_character_references_are_not_hex_colours(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, "<p>Loading&#8230; done &#8212; &#169;</p>")) == []


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
        # JS/TS style objects
        ('<p style={{ color: "red" }}>x</p>', "a.tsx", 1),
        ("const s = { backgroundColor: 'blue', borderTopColor: \"green\" };", "a.ts", 2),
        ('const s = { fill: dark ? "white" : "pink" };', "a.ts", 1),
        ('const s = { caretColor: "red", textDecoration: "wavy pink", columnRule: "teal" };', "a.ts", 3),
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


def test_colour_words_in_ui_copy_are_not_colours(tmp_path: Path) -> None:
    copy = "\n".join(
        [
            "<p>Ordered items stay red-flagged until the green light.</p>",
            'const note = "Orange is the new red-flagged"; // blue sky',
            'const row = { title: "Green light", label: "Red flag" };',
            # a style key's value ends at the comma: the next key's text is not a colour
            '{ border: "1px solid #000", note: "Red alert" }',
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


def test_colour_function_names_must_stand_alone(tmp_path: Path) -> None:
    code = "get_color(x); bg-color(y); mycolor(z); const c = pick(color);"
    assert violations(_file(tmp_path, code)) == []
