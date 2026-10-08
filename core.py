"""
CBM Article Converter - conversion core.
Version 1.0.0
"""
import re, math, copy, datetime, pathlib, unicodedata, zipfile
import mammoth
from bs4 import BeautifulSoup, Tag, NavigableString

VERSION = "1.5.1"

# Kept so anything that still asks for a build number gets something sensible.
BUILD = VERSION
WORDS_PER_MINUTE = 200


# ---------------------------------------------------------------- options ---
# Everything adjustable lives here. "Reset to defaults" restores exactly this,
# so as the house style settles these values move and everyone follows.

PROFILE_BASE = "/profile/"


def author_slug(name):
    """'Scott N. Callaham' -> 'scott-n-callaham'. The same rule every time, so
    the link the article carries and the page the designer makes agree."""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text


def split_authors(text):
    """Names as the editor wrote them, in the editor's order."""
    text = re.sub(r"(?i)^\s*(?:by|written by)\s+", "", str(text).strip())
    parts = re.split(r"\s*(?:,|;|&|\band\b)\s*", text)
    return [p.strip() for p in parts if p.strip()]


BLOCK_LABELS = {
    "byline": "Byline (By \u2026)",
    "blurb": "Blurb",
    "note": "Article note",
    "read": "Reading time",
    "body": "Article body",
    "share": "Share this article",
    "bio": "Author bio",
}
FIXED_BLOCK = "body"          # always present; may be moved
PINNED_LAST = "footnotes"     # generated from the body, so nothing follows it

DEFAULTS = {
    "order": ["byline", "blurb", "note", "read", "body", "share", "bio"],
    "include": {"byline": True, "blurb": True, "note": True, "read": True,
                "body": True, "share": False, "bio": True},
    "profile_base": PROFILE_BASE,
    "known_authors": [],
    "style": {},
    # Left to the site by default: heading alignment is the only thing the
    # article declares that Squarespace's own Styles menu also controls.
    "heading_align": "none",        # left, center, right, or none
    "words_per_minute": 200,
    "output": "beside",             # beside the original, or a chosen folder
    "output_folder": "",
    "check_at_startup": True,
}


def options(settings=None):
    """Settings merged over the defaults, so a missing key is never fatal."""
    data = dict(DEFAULTS)
    data["include"] = dict(DEFAULTS["include"])
    data["order"] = list(DEFAULTS["order"])
    for key, value in (settings or load_settings()).items():
        if key == "include" and isinstance(value, dict):
            data["include"].update(value)
        elif key == "order" and isinstance(value, list):
            known = [b for b in value if b in BLOCK_LABELS]
            for b in DEFAULTS["order"]:
                if b not in known:
                    known.append(b)
            data["order"] = known
        elif key in data:
            data[key] = value
    data["include"][FIXED_BLOCK] = True
    return data


def non_default(opts):
    """The settings that differ from the defaults, for the file's stamp."""
    out = []
    if opts["order"] != DEFAULTS["order"]:
        out.append("order=" + ",".join(opts["order"]))
    off = [b for b, on in opts["include"].items() if not on and DEFAULTS["include"].get(b)]
    on = [b for b, v in opts["include"].items() if v and not DEFAULTS["include"].get(b)]
    if off:
        out.append("off=" + ",".join(sorted(off)))
    if on:
        out.append("on=" + ",".join(sorted(on)))
    for key in ("heading_align", "words_per_minute"):
        if opts[key] != DEFAULTS[key]:
            out.append(f"{key}={opts[key]}")
    return out


# ------------------------------------------------- the look of an article ---
# One schema drives three things: the controls in the Designer panel, the
# stylesheet the app exports, and the copy attached to the .html for checking.
# Adding a control here is enough; nothing else needs changing.

STYLE_SCHEMA = [
    ("Blurb", [
        ("blurb_size", "Size", "em", 1.15),
        ("blurb_line", "Line height", "num", 1.5),
        ("blurb_align", "Alignment", "align", "center"),
        ("blurb_italic", "Italic", "bool", False),
    ]),
    ("Article note", [
        ("note_size", "Size", "em", 1.0),
        ("note_align", "Alignment", "align", "center"),
        ("note_italic", "Italic", "bool", True),
    ]),
    ("Byline", [
        ("byline_size", "Size", "em", 1.0),
        ("byline_align", "Alignment", "align", "center"),
        ("byline_italic", "Italic", "bool", False),
    ]),
    ("Reading time", [
        ("read_size", "Size", "em", 0.78),
        ("read_spacing", "Letter spacing", "em", 0.09),
        ("read_align", "Alignment", "align", "center"),
        ("read_caps", "Capitals", "bool", True),
        ("read_clock", "Show the clock", "bool", True),
    ]),
    ("Author bio", [
        ("bio_size", "Size", "em", 0.9),
        ("bio_align", "Alignment", "align", "center"),
        ("bio_italic", "Italic", "bool", True),
    ]),
    ("Headings", [
        ("heading_align", "Alignment", "align_none", "none"),
        ("h4_italic", "Heading 4 italic", "bool", True),
    ]),
    ("Verse", [
        ("verse_indent", "Indent", "em", 2.5),
        ("verse_hang", "Hanging indent", "em", 1.25),
    ]),
    ("Pull quotes", [
        ("pq_text_size", "Text size", "em", 1.25),
        ("pq_line", "Line height", "num", 1.4),
        ("pq_italic", "Italic", "bool", True),
        ("pq_border", "Rule weight", "px", 1),
        ("pq_width", "Width when floated", "pct", 38),
        ("pq_outdent", "Outdent", "in", 0.75),
        ("pq_float_at", "Float at or above", "px", 900),
    ]),
    ("Share icons", [
        ("share_size", "Icon size", "em", 1.15),
        ("share_gap", "Spacing", "em", 0.45),
        ("share_label", "Label above the row", "text", "Share this article"),
    ]),
    ("Rules", [
        ("rule_weight", "Weight", "px", 1),
        ("rule_opacity", "Opacity", "pct", 25),
        ("rule_space", "Space above and below", "em", 1.6),
    ]),
    ("Pictures", [
        ("fig_space", "Space above and below", "em", 1.4),
        ("fig_caption_size", "Caption size", "em", 0.85),
        ("fig_caption_align", "Caption alignment", "align", "center"),
        ("fig_float_at", "Wrap text at or above", "px", 700),
    ]),
    ("Footnotes", [
        ("fn_weight", "Number weight", "weight", 600),
    ]),
]

STYLE_DEFAULTS = {key: default
                  for _group, items in STYLE_SCHEMA
                  for key, _label, _kind, default in items}


def style_values(opts=None):
    """The look settings, with anything unset falling back to the default."""
    opts = opts if opts is not None else options()
    values = dict(STYLE_DEFAULTS)
    for key, value in (opts.get("style") or {}).items():
        if key in values:
            values[key] = value
    # Heading alignment is also a conversion setting, so keep the two agreed.
    if opts.get("heading_align"):
        values["heading_align"] = opts["heading_align"]
    return values

# Word paragraph styles -> internal roles. Matched loosely: a style called
# "Verse Block" counts as verse, "Side-Bar" as a pull quote.
ROLE_PATTERNS = [
    ("title",      r"title"),
    ("author_bio", r"author.?bio"),
    ("author",     r"author|byline"),
    ("blurb",      r"blurb|deck|summary|standfirst"),
    ("note",       r"article.?note"),
    ("pull_left",  r"left.?side.?bar"),
    ("pull_right", r"right.?side.?bar"),
    ("pull",       r"side.?bar|pull.?quote"),
    ("verse",      r"verse|poetry"),
    ("quote",      r"block.?text|block.?quote|quotation"),
]

STYLE = {
    "blurb":   "font-size:1.15em; line-height:1.5;",
    "note":    "font-style:italic;",
    "bio":     "text-align:center; font-style:italic; font-size:0.9em;",
    "read":    "text-align:center; font-size:0.78em; letter-spacing:0.09em; text-transform:uppercase;",
    "verse":   "margin-left:2.5em; text-indent:-1.25em;",
    "h2":      "text-align:center;",
    "h3":      "text-align:center;",
    "h4":      "text-align:left; font-style:italic;",
    "rule":    "border:none; border-top:1px solid currentColor; opacity:0.25; margin:1.6em 0;",
    "pq":      ("max-width:32em; margin:2em auto; padding:0.8em 0; "
                "border-top:1px solid currentColor; border-bottom:1px solid currentColor; "
                "text-align:center;"),
    "pqtext":  "margin:0 0 0.5em; font-style:italic; font-size:1.25em; line-height:1.4;",
    "pqshare": "margin:0; font-size:0.75em; letter-spacing:0.05em; text-transform:uppercase;",
}


# Every rule is scoped to .cbm-article, so none of it can reach the rest of
# the page. That is what makes a <style> block safe inside a Code Block, and
# it means floats and media queries work without anything set up site-wide.
CSS_BEGIN = "/* ===== BEGIN CBM article styles - generated, do not edit below ===== */"
CSS_END = "/* ===== END CBM article styles ===== */"


def article_css(opts=None, wrap=True):
    """
    The article's styling, built from the look settings. Everything is
    scoped to .cbm-article so none of it can reach the rest of the page,
    and colours are never named: currentColor follows the theme.
    """
    v = style_values(opts)
    italic = lambda on: "italic" if on else "normal"
    if v["heading_align"] == "none":
        headings = "/* heading alignment left to the site */"
    else:
        headings = (f".cbm-article h2, .cbm-article h3 {{ text-align:{v['heading_align']}; }}\n"
                    f".cbm-article h4 {{ text-align:{v['heading_align']}; "
                    f"font-style:{italic(v['h4_italic'])}; }}")
    css = f"""{CSS_BEGIN}
.cbm-article .cbm-blurb {{
  font-size:{v['blurb_size']}em; line-height:{v['blurb_line']};
  text-align:{v['blurb_align']}; font-style:{italic(v['blurb_italic'])};
}}
.cbm-article .cbm-note {{
  font-size:{v['note_size']}em; text-align:{v['note_align']};
  font-style:{italic(v['note_italic'])};
}}
.cbm-article .cbm-byline {{
  font-size:{v['byline_size']}em; text-align:{v['byline_align']};
  font-style:{italic(v['byline_italic'])}; margin:0 0 0.6em;
}}
.cbm-article .cbm-byline a {{ color:inherit; }}
.cbm-article .cbm-read {{
  font-size:{v['read_size']}em; letter-spacing:{v['read_spacing']}em;
  text-align:{v['read_align']};
  text-transform:{'uppercase' if v['read_caps'] else 'none'};
}}
.cbm-article .cbm-clock {{
  width:1em; height:1em; vertical-align:-0.13em; margin-right:0.45em;
  display:{'inline-block' if v['read_clock'] else 'none'};
}}
.cbm-article .cbm-bio {{
  font-size:{v['bio_size']}em; text-align:{v['bio_align']};
  font-style:{italic(v['bio_italic'])};
}}
{headings}
.cbm-article .cbm-verse {{
  margin-left:{v['verse_indent']}em; text-indent:-{v['verse_hang']}em;
}}
.cbm-article [lang="he"] {{ text-align:right; }}
.cbm-article .cbm-verse[lang="he"] {{ margin-left:0; margin-right:{v['verse_indent']}em; }}
.cbm-article .cbm-rule {{
  border:none; border-top:{v['rule_weight']}px solid currentColor;
  opacity:{float(v['rule_opacity']) / 100:.2f}; margin:{v['rule_space']}em 0;
}}
.cbm-article .cbm-pullquote {{
  max-width:32em; margin:2em auto; padding:0.8em 0;
  border-top:{v['pq_border']}px solid currentColor;
  border-bottom:{v['pq_border']}px solid currentColor;
  text-align:center;
}}
.cbm-article .cbm-pullquote-text {{
  margin:0 0 0.5em; font-size:{v['pq_text_size']}em;
  line-height:{v['pq_line']}; font-style:{italic(v['pq_italic'])};
}}
.cbm-article .cbm-share {{ margin:0; line-height:1; }}
.cbm-article .cbm-share a {{
  display:inline-block; margin:0 {v['share_gap']}em; color:currentColor;
  text-decoration:none; opacity:0.75;
}}
.cbm-article .cbm-share a:hover {{ opacity:1; }}
.cbm-article .cbm-share svg {{
  width:{v['share_size']}em; height:{v['share_size']}em; vertical-align:middle;
}}
.cbm-article .cbm-share-article {{ text-align:center; margin:1.2em 0; line-height:1; }}
.cbm-article .cbm-share-article::before {{
  content:"{v['share_label']}"; display:block; font-size:0.72em;
  letter-spacing:0.09em; text-transform:uppercase; opacity:0.7;
  margin-bottom:0.5em;
}}
.cbm-article .cbm-figure {{
  margin:{v['fig_space']}em auto; max-width:100%;
}}
.cbm-article .cbm-figure img {{ width:100%; height:auto; display:block; }}
.cbm-article .cbm-figure figcaption {{
  font-size:{v['fig_caption_size']}em; text-align:{v['fig_caption_align']};
  opacity:0.8; margin-top:0.5em;
}}
.cbm-article .cbm-image-missing {{
  border:2px dashed currentColor; padding:1.4em 1em; text-align:center;
  font-size:0.85em; line-height:1.7; opacity:0.85;
}}
.cbm-article .cbm-image-missing strong {{
  display:block; letter-spacing:0.08em;
}}
.cbm-article .cbm-image-missing span {{ display:block; font-size:0.9em; }}
.cbm-article .cbm-footnotes {{ list-style:none; padding-left:0; }}
.cbm-article .footnote-back {{ text-decoration:none; font-weight:{v['fn_weight']}; }}

/* Floated into the margin on a wide screen, alternating down the page.
   Narrower than this they stay centred blocks: a narrow floating box is
   unreadable. */
@media (min-width: {v['pq_float_at']}px) {{
  .cbm-article .cbm-pullquote {{
    width:{v['pq_width']}%; max-width:none; margin:0.4em 0 1em 0; text-align:left;
  }}
  .cbm-article .cbm-pq-left {{
    float:left; margin-left:-{v['pq_outdent']}in; margin-right:1.6em;
  }}
  .cbm-article .cbm-pq-right {{
    float:right; margin-right:-{v['pq_outdent']}in; margin-left:1.6em;
  }}
}}
/* Text wraps round a picture only when there is room for it to read. */
@media (min-width: {v['fig_float_at']}px) {{
  .cbm-article .cbm-figure-left {{
    float:left; margin:0.4em 1.6em 0.9em 0;
  }}
  .cbm-article .cbm-figure-right {{
    float:right; margin:0.4em 0 0.9em 1.6em;
  }}
}}
/* Narrower than that, a picture takes the full width. The width set on each
   figure is particular to that picture, so overriding it needs !important. */
@media (max-width: {int(v['fig_float_at']) - 1}px) {{
  .cbm-article .cbm-figure {{ width:100% !important; float:none; }}
}}
/* A picture and a pull quote should never float alongside each other. */
.cbm-article .cbm-figure-left + .cbm-pq-left,
.cbm-article .cbm-pq-left + .cbm-figure-left {{ clear:left; }}
.cbm-article .cbm-figure-right + .cbm-pq-right,
.cbm-article .cbm-pq-right + .cbm-figure-right {{ clear:right; }}

.cbm-article h2, .cbm-article h3, .cbm-article h4,
.cbm-article .cbm-rule, .cbm-article .cbm-footnotes,
.cbm-article section {{ clear:both; }}
{CSS_END}"""
    return f"<style>\n{css}\n</style>" if wrap else css



# Share icons, drawn inline so they take the text colour and need no files.
ICONS = {
    "x": ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
          '<path d="M18.9 2H22l-7.2 8.3L23.3 22h-6.6l-5.2-6.8L5.6 22H2.5l7.7-8.8L1.1 2h6.8'
          'l4.7 6.2zm-1.1 18h1.7L7.3 3.8H5.5z"/></svg>'),
    "fb": ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
           '<path d="M14 9h3V6h-3c-2.2 0-4 1.8-4 4v2H8v3h2v7h3v-7h3l1-3h-4v-2'
           'c0-.6.4-1 1-1z"/></svg>'),
    "email": ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
              'aria-hidden="true"><rect x="2.5" y="4.5" width="19" height="15" rx="2"/>'
              '<path d="M3 6l9 6.5L21 6" stroke-linecap="round" stroke-linejoin="round"/></svg>'),
}

CLOCK = ('<svg width="1em" height="1em" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
         'stroke-width="1.5" aria-hidden="true" class="cbm-clock">'
         '<circle cx="8" cy="8" r="6.4" /><path d="M8 4.3V8.2l2.5 1.5" stroke-linecap="round" '
         'stroke-linejoin="round" /></svg>')

SHARE_SCRIPT = """
<script>
(function () {
  var here = window.location.href.split('#')[0];
  var url = encodeURIComponent(here);
  var rows = document.querySelectorAll('.cbm-share');
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    // A row inside a pull quote shares that sentence; the row that belongs
    // to the whole article shares the article's own title.
    var box = row.closest ? row.closest('.cbm-pullquote') : null;
    var quote = box ? box.querySelector('.cbm-pullquote-text') : null;
    var saying = quote ? quote.textContent.trim() : (document.title || '').trim();
    var text = encodeURIComponent(saying ? '\u201c' + saying + '\u201d' : '');
    var x = row.querySelector('.cbm-share-x');
    var f = row.querySelector('.cbm-share-fb');
    var e = row.querySelector('.cbm-share-email');
    if (x) x.href = 'https://twitter.com/intent/tweet?text=' + text + '&url=' + url;
    if (f) f.href = 'https://www.facebook.com/sharer/sharer.php?u=' + url;
    if (e) e.href = 'mailto:?subject=' + encodeURIComponent(document.title) +
                    '&body=' + text + '%20' + url;
  }
})();
</script>
"""

HEB = re.compile(r'[\u0590-\u05FF\uFB1D-\uFB4F]')
GRK = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
LAT = re.compile(r'[A-Za-z]')


def role_of(name):
    """Map a style or class name to an internal role."""
    n = re.sub(r"[\s_]+", " ", str(name or "")).lower()
    for role, pattern in ROLE_PATTERNS:
        if re.search(pattern, n):
            return role
    return None


def plain(node):
    t = node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node)
    return re.sub(r"\s+", " ", t).strip()


def norm(text):
    t = (text.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'")
             .replace("\u201c", '"').replace("\u201d", '"')
             .replace("\u2013", "-").replace("\u2014", "-"))
    return re.sub(r"\s+", " ", t).strip().lower()


def fragments(text):
    """Split a quote on ellipses and drop [bracketed] additions, longest first."""
    n = re.sub(r"\[[^\]]*\]", "", norm(text))
    parts = re.split(r"\u2026|\.\s*\.\s*\.", n)
    out = [p.strip(" .,;:\"'") for p in parts]
    return sorted([p for p in out if len(p.split()) >= 4], key=len, reverse=True)


# ---------------------------------------------------------------- readers ---

def read_docx(path):
    """
    Word -> HTML, with house styles mapped to marker elements.

    Pictures are kept aside rather than written into the page: the reader's
    habit is to encode each one as text inside the HTML, which turns a
    one-megabyte photograph into a megabyte of article.
    """
    rules = [f"p[style-name='Heading {i}'] => h{i}:fresh" for i in range(1, 7)]
    rules.append("p[style-name='Caption'] => div.cbm-caption:fresh")
    for style in docx_style_names(path):
        role = role_of(style)
        if role and "'" not in style:
            rules.append(f"p[style-name='{style}'] => div.cbm-{role}:fresh")

    kept = []

    def keep(image):
        index = len(kept)
        extension = {
            "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
            "image/tiff": "tif", "image/bmp": "bmp", "image/x-emf": "emf",
            "image/webp": "webp",
        }.get(image.content_type, "img")
        with image.open() as handle:
            data = handle.read()
        name = f"image{index + 1}.{extension}"
        kept.append({"name": name, "data": data, "type": image.content_type,
                     "alt": (getattr(image, "alt_text", "") or "").strip()})
        return {"src": name, "data-cbm-picture": str(index)}

    with open(path, "rb") as fh:
        result = mammoth.convert_to_html(
            fh, style_map="\n".join(rules),
            convert_image=mammoth.images.img_element(keep))
    return result.value, [str(m) for m in result.messages], kept


def docx_style_names(path):
    """Every paragraph style name defined in the document."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/styles.xml").decode("utf-8", "replace")
    except Exception:
        return []
    names = []
    for m in re.finditer(r"<w:style\b[^>]*w:type=\"paragraph\"[^>]*>(.*?)</w:style>", xml, re.S):
        nm = re.search(r'<w:name w:val="([^"]+)"', m.group(1))
        if nm:
            names.append(nm.group(1))
    return names


def read_indesign(path):
    """InDesign export -> HTML, with its stylesheet read for character roles."""
    html = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    roles = {}
    link = re.search(r'<link[^>]*href="([^"]+\.css)"', html)
    css_found = False
    if link:
        css_path = pathlib.Path(path).parent.joinpath(*link.group(1).split("/"))
        if css_path.exists():
            css_found = True
            css = css_path.read_text(encoding="utf-8", errors="replace")
            for name, body in re.findall(r"\.([A-Za-z_][\w\-]*)\s*\{([^}]*)\}", css):
                b = body.lower()
                if re.search(r"font-style:\s*italic", b):          roles[name] = "em"
                elif re.search(r"font-weight:\s*(bold|700)", b):   roles[name] = "strong"
                elif re.search(r"vertical-align:\s*super", b):     roles[name] = "sup"
                elif re.search(r"white-space:\s*nowrap", b):       roles[name] = "nowrap"
    # InDesign tags No Break runs but often writes no rule for them.
    for cls in re.findall(r'class="([^"]+)"', html):
        for part in cls.split():
            if re.match(r"(?i)^no.?break$", part):
                roles[part] = "nowrap"
    return html, roles, css_found


# ------------------------------------------------------------ normalising ---

def apply_indesign_roles(soup, roles):
    """Turn InDesign's meaningless class names into real markup."""
    # No Break first, keeping the span so other classes on it still apply.
    for span in soup.find_all("span"):
        classes = span.get("class") or []
        if any(roles.get(c) == "nowrap" for c in classes):
            for t in span.find_all(string=True):
                t.replace_with(str(t).replace(" ", "\u00a0"))
    # Character styles -> em / strong / sup
    for span in list(soup.find_all("span")):
        classes = span.get("class") or []
        role = next((roles.get(c) for c in classes if roles.get(c) in ("em", "strong", "sup")), None)
        if role:
            span.name = role
            del span["class"]
    # Paragraph styles -> headings and roles. InDesign's Heading-1 is the
    # article's top section level, which is h2 here: the page title is
    # supplied by Squarespace, not by the article.
    heading_for = {"heading-1": "h2", "heading-2": "h3", "heading-3": "h4",
                   "heading-4": "h5"}
    for p in soup.find_all("p"):
        name = " ".join(p.get("class") or []).lower()
        hit = next((tag for key, tag in heading_for.items() if key in name), None)
        if hit:
            p.name = hit
            del p["class"]
            continue
        role = role_of(name)
        if role:
            p["data-role"] = role
        if p.has_attr("class"):
            del p["class"]
    # Drop the frame wrappers and any leftover classes
    for div in list(soup.find_all("div")):
        div.unwrap()
    for el in soup.find_all(True):
        for attr in ("class", "lang"):
            if el.has_attr(attr) and attr == "class":
                del el[attr]


def apply_docx_roles(soup):
    """mammoth wrote marker divs; convert them to tagged paragraphs."""
    for div in list(soup.find_all("div")):
        classes = div.get("class") or []
        marker = next((c[4:] for c in classes if c.startswith("cbm-")), None)
        if not marker:
            div.unwrap()
            continue
        inner = div.find(["p", "blockquote"])
        text_holder = inner if inner else div
        new = soup.new_tag("p")
        new["data-role"] = marker
        for child in list(text_holder.contents):
            new.append(child.extract())
        div.replace_with(new)


def tidy(soup):
    """
    Clear out what the exporters leave behind: empty spans, and the anchor
    points InDesign drops in for its own cross-references, which nothing in
    a converted article links to.
    """
    for a in list(soup.find_all("a")):
        if not a.get("href") and not a.get_text(strip=True) and not a.find(True):
            a.decompose()
    for span in list(soup.find_all("span")):
        if not span.attrs:
            span.unwrap()
    for p in list(soup.find_all("p")):
        if not p.get_text(strip=True) and not p.find(["img", "br", "svg"]):
            p.decompose()


def label_front_matter(soup):
    """Recognise 'Title:', 'Author:' and 'Blurb:' labels before the first heading."""
    for p in soup.find_all("p"):
        if p.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"]):
            break
        if p.has_attr("data-role"):
            continue
        text = plain(p)
        m = re.match(r"(?i)^(title|author bio|author|blurb)\s*:\s*(.*)$", text)
        if not m:
            continue
        role = {"title": "title", "author": "author",
                "author bio": "author_bio", "blurb": "blurb"}[m.group(1).lower()]
        p["data-role"] = role
        p.clear()
        p.append(NavigableString(m.group(2)))


def fix_self_links(soup):
    """InDesign writes footnote links as file.html#id; make them plain anchors."""
    for a in soup.find_all("a", href=True):
        a["href"] = re.sub(r'^[^"/?#:]+\.html#', "#", a["href"])


# ---------------------------------------------------------------- features ---

def tidy_footnote_callouts(soup):
    """
    The raised number in the text.

    Two things to undo. The Word reader brackets every reference, giving
    "[1]" where house style wants a bare numeral. And a reference that an
    author also superscripted by hand arrives wrapped twice, which shrinks
    the number to almost nothing.
    """
    brackets = nested = 0
    for sup in list(soup.find_all("sup")):
        inner = sup.find("sup")
        while inner is not None:
            inner.unwrap()
            nested += 1
            inner = sup.find("sup")
    for link in soup.find_all("a", href=True):
        if not link.find_parent("sup"):
            continue
        text = link.get_text()
        stripped = re.sub(r"^\s*\[\s*(.+?)\s*\]\s*$", r"\1", text)
        if stripped != text:
            link.string = stripped
            brackets += 1
    return brackets, nested


def number_footnotes(soup):
    """Make each footnote's number the link back to its callout."""
    notes = [li for li in soup.find_all("li") if re.search(r"(fn\d|footnote)", li.get("id") or "")]
    linked = 0
    for li in notes:
        fid = li["id"]
        # the callout that points here
        ref = soup.find("a", href="#" + fid)
        if ref is not None and not ref.get("id"):
            ref["id"] = "ref-" + fid
        back_target = ref.get("id") if ref is not None else None
        # remove any existing back-link (Pandoc's arrow, InDesign's number)
        number = None
        for a in list(li.find_all("a", href=True)):
            href = a["href"]
            if href.startswith("#") and ("backlink" in href or "fnref" in href or "ref-" in href):
                txt = plain(a)
                if re.fullmatch(r"\d+", txt):
                    number = txt
                if not back_target:
                    back_target = href.lstrip("#")
                a.decompose()
        if number is None:
            number = str(notes.index(li) + 1)
        # strip a stray full stop left behind by InDesign's "1." construction
        first = li.find(string=True)
        if first and re.match(r"^\s*\.\s*", str(first)):
            first.replace_with(re.sub(r"^\s*\.\s*", " ", str(first)))
        if not back_target:
            continue
        target = li.find("p") or li
        link = soup.new_tag("a", href="#" + back_target)
        link["class"] = ["footnote-back"]
        link.string = f"{number}."
        target.insert(0, NavigableString("\u00a0"))
        target.insert(0, link)
        linked += 1
    # the list itself shows no automatic numbers
    for li in notes:
        ol = li.find_parent("ol")
        if ol is not None:
            ol["class"] = ["cbm-footnotes"]
    return linked


def outbound_links_new_tab(soup):
    n = 0
    for a in soup.find_all("a", href=True):
        if re.match(r"https?://", a["href"]) and not a.get("target"):
            a["target"] = "_blank"
            a["rel"] = "noopener"
            n += 1
    return n


def style_headings(soup):
    heads = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if len([h for h in heads if h.name == "h1"]) > 1:
        for h in sorted(heads, key=lambda x: x.name, reverse=True):
            level = int(h.name[1])
            if level < 6:
                h.name = f"h{level + 1}"
    counts = {}
    for h in soup.find_all(["h2", "h3", "h4"]):
        counts[h.name] = counts.get(h.name, 0) + 1
    return counts


HEBREW_RUN = re.compile(
    r"[\u0590-\u05FF\uFB1D-\uFB4F]+"
    r"(?:[\s\u00a0\u05BE\u05C0\u05C3\u05C6-]+[\u0590-\u05FF\uFB1D-\uFB4F]+)*")

SKIP_INSIDE = {"style", "script", "svg", "code", "pre"}


def tag_inline_hebrew(soup):
    """
    Wrap Hebrew inside an otherwise English sentence in <span lang="he">.

    Whole Hebrew paragraphs are handled separately. This catches the single
    word or phrase, which is the common case in these articles and which a
    paragraph-level rule cannot reach.
    """
    wrapped = 0
    for text in list(soup.find_all(string=True)):
        parent = text.parent
        if parent is None or parent.name in SKIP_INSIDE:
            continue
        if parent.find_parent(attrs={"lang": "he"}) or parent.get("lang") == "he":
            continue
        value = str(text)
        if not HEB.search(value):
            continue
        pieces, last = [], 0
        for m in HEBREW_RUN.finditer(value):
            if m.start() > last:
                pieces.append(NavigableString(value[last:m.start()]))
            span = soup.new_tag("span")
            span["lang"] = "he"
            span.string = m.group(0)
            pieces.append(span)
            wrapped += 1
            last = m.end()
        if last < len(value):
            pieces.append(NavigableString(value[last:]))
        if pieces:
            text.replace_with(*pieces)
    return wrapped


def mark_languages(soup):
    """A mostly-Hebrew paragraph reads right to left; Greek is tagged only."""
    rtl = 0
    for p in soup.find_all("p"):
        if p.get("lang"):
            continue
        t = plain(p)
        heb, grk, lat = len(HEB.findall(t)), len(GRK.findall(t)), len(LAT.findall(t))
        if heb > lat and heb > 0:
            p["lang"], p["dir"] = "he", "rtl"
            rtl += 1
        elif grk > lat and grk > 0:
            p["lang"] = "el"
    return rtl


# ------------------------------------------------------------- pull quotes ---

def build_byline(soup, opts):
    """
    "By Chris Burnett, Scott Callaham, Kyle Dunham and Josh Sherrill", each
    name linked to that author's profile page. The names and their order come
    from the Word Author style; the link is the name slugified, so the article
    and the page agree without anything being looked up.
    """
    source = soup.find("p", attrs={"data-role": "author"})
    if source is None:
        return None, []
    names = split_authors(plain(source))
    source.decompose()
    if not names:
        return None, []
    base = opts.get("profile_base") or PROFILE_BASE
    para = soup.new_tag("p")
    para["class"] = ["cbm-byline"]
    para.append(NavigableString("By "))
    for index, name in enumerate(names):
        if index:
            if index == len(names) - 1:
                para.append(NavigableString(" and " if len(names) == 2 else ", and "))
            else:
                para.append(NavigableString(", "))
        link = soup.new_tag("a", href=base.rstrip("/") + "/" + author_slug(name))
        link.string = name
        para.append(link)
    return para, names


def build_figures(soup, pictures):
    """
    Turn each picture into a figure that says what belongs there.

    Nothing is embedded. The article carries a marked block naming the file,
    which is replaced with the real picture once it has been uploaded and has
    an address. A caption beside the picture in Word comes with it.
    """
    made, missing_alt = [], []
    for image in list(soup.find_all("img")):
        index = image.get("data-cbm-picture")
        detail = {}
        if index is not None and index.isdigit() and int(index) < len(pictures):
            detail = pictures[int(index)]
        filename = detail.get("name") or pathlib.Path(
            str(image.get("src") or "image")).name
        alt = (image.get("alt") or detail.get("alt") or "").strip()

        figure = soup.new_tag("figure")
        classes = ["cbm-figure"]
        side = detail.get("side")
        if side:
            classes.append(f"cbm-figure-{side}")
        figure["class"] = classes
        percent = detail.get("percent")
        if percent and percent < 100:
            # Per-picture geometry, not house styling: it belongs to this one
            # photograph and cannot live in a shared stylesheet.
            figure["style"] = f"width:{percent}%"
        figure["data-cbm-file"] = filename
        if alt:
            figure["data-cbm-alt"] = alt
        else:
            missing_alt.append(filename)

        slot = soup.new_tag("div")
        slot["class"] = ["cbm-image-missing"]
        size = ""
        if detail.get("width_in"):
            size = f" \u2014 {detail['width_in']} \u00d7 {detail['height_in']} in"
        strong = soup.new_tag("strong")
        strong.string = "PICTURE GOES HERE"
        slot.append(strong)
        slot.append(NavigableString(filename + size))
        note = soup.new_tag("span")
        note.string = "Replace this block with the picture, or delete it."
        slot.append(note)
        figure.append(slot)

        # A Word caption sitting either side of the picture comes with it.
        holder = image.parent
        target = holder if holder is not None and holder.name == "p" and \
            not holder.get_text(strip=True) else image
        caption = None
        for probe in (target.find_next_sibling(), target.find_previous_sibling()):
            if isinstance(probe, Tag) and probe.get("data-role") == "caption":
                caption = probe
                break
        if caption is not None:
            cap = soup.new_tag("figcaption")
            for child in list(caption.contents):
                cap.append(child.extract())
            figure.append(cap)
            caption.decompose()

        target.replace_with(figure)
        made.append(figure)
    return made, missing_alt


def share_row(soup, classes=("cbm-share",)):
    """The three icons, in a paragraph. Used by pull quotes and by the
    article-wide row, so they cannot drift apart."""
    row = soup.new_tag("p")
    row["class"] = list(classes)
    for cls, icon, label in (("cbm-share-x", "x", "Share on X"),
                             ("cbm-share-fb", "fb", "Share on Facebook"),
                             ("cbm-share-email", "email", "Share by email")):
        a = soup.new_tag("a", href="#")
        a["class"] = [cls]
        a["title"] = label
        a["aria-label"] = label
        if cls != "cbm-share-email":
            a["target"], a["rel"] = "_blank", "noopener"
        a.append(BeautifulSoup(ICONS[icon], "html.parser"))
        row.append(a)
    return row


def build_pull_quotes(soup):
    """Turn tagged paragraphs into aside blocks with share links."""
    made = []
    for p in list(soup.find_all("p", attrs={"data-role": re.compile(r"^pull")})):
        role = p["data-role"]
        inner = p.find("blockquote") or p.find("p")
        content = inner if inner is not None else p
        aside = soup.new_tag("aside")
        aside["class"] = ["cbm-pullquote"]
        if role in ("pull_left", "pull_right"):
            aside["data-side"] = role.split("_")[1]
        text_p = soup.new_tag("p")
        text_p["class"] = ["cbm-pullquote-text"]
        for child in list(content.contents):
            text_p.append(child.extract())
        aside.append(text_p)
        aside.append(share_row(soup))
        p.replace_with(aside)
        made.append(aside)
    return made


def relocate_pull_quotes(soup, quotes):
    """
    InDesign pushes unanchored frames out of the article, so quotes arrive in a
    heap - before the first heading or after the last. Match each to the
    paragraph it quotes and move it there. Quotes an editor placed are left be.
    """
    if not quotes:
        return 0, []
    blocks = [el for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6",
                                          "blockquote", "aside", "section", "ol"])
              if el.find_parent("aside") is None and el.find_parent("li") is None]
    heads = [i for i, el in enumerate(blocks) if re.fullmatch(r"h[1-6]", el.name)]
    idx = {id(el): i for i, el in enumerate(blocks)}
    positions = [idx[id(q)] for q in quotes if id(q) in idx]
    if not heads or not positions:
        return 0, []
    piled = all(p > heads[-1] for p in positions) or all(p < heads[0] for p in positions)
    # a quote already sitting after the paragraph it quotes is where it belongs
    if piled:
        all_home = True
        for q in quotes:
            prev = q.find_previous("p")
            body = norm(plain(prev)) if prev is not None else ""
            text = plain(q.find("p", class_="cbm-pullquote-text"))
            if not any(f in body for f in fragments(text)):
                all_home = False
        if all_home:
            piled = False
    if not piled:
        return 0, []
    paragraphs = [el for el in blocks if el.name == "p"
                  and el.find_parent("aside") is None
                  and not el.has_attr("data-role")]
    moved, orphans = 0, []
    for q in quotes:
        text = plain(q.find("p", class_="cbm-pullquote-text"))
        target = None
        for frag in fragments(text):
            for para in paragraphs:
                if frag in norm(plain(para)):
                    target = para
                    break
            if target is not None:
                break
        if target is None:
            orphans.append(q)
            continue
        # A quote beside the final paragraph has nothing to wrap it and
        # would hang below the article, so it goes above that paragraph
        # instead of after it.
        if target is paragraphs[-1]:
            target.insert_before(q.extract())
        else:
            target.insert_after(q.extract())
        moved += 1
    return moved, orphans


def alternate_sides(soup):
    n = 0
    for aside in soup.find_all("aside", class_="cbm-pullquote"):
        side = aside.get("data-side")
        if not side:
            n += 1
            side = "left" if n % 2 == 1 else "right"
        if aside.has_attr("data-side"):
            del aside["data-side"]
        aside["class"] = ["cbm-pullquote", f"cbm-pq-{side}"]


# ------------------------------------------------------------ assembly -----

def reading_minutes(soup, per_minute=200):
    clone = BeautifulSoup(str(soup), "html.parser")
    for el in clone.find_all(["aside", "section"]):
        el.decompose()
    for el in clone.find_all("p", attrs={"data-role": True}):
        el.decompose()
    for el in clone.find_all("ol"):
        if el.find("li", id=re.compile(r"(fn\d|footnote)")):
            el.decompose()
    words = [w for w in re.split(r"\s+", clone.get_text(" ")) if re.search(r"\w", w)]
    return len(words), max(1, math.ceil(len(words) / max(1, per_minute))) if words else 0


def footnote_start(soup):
    """The element the footnotes begin with, whichever track produced them."""
    li = soup.find("li", id=re.compile(r"(fn\d|footnote)"))
    if li is None:
        return None
    node = li.find_parent("ol") or li
    for _ in range(3):
        parent = node.parent
        if isinstance(parent, Tag) and parent.name in ("section", "aside", "div"):
            node = parent
        else:
            break
    prev = node.find_previous_sibling()
    if isinstance(prev, Tag) and prev.name == "hr":
        node = prev
    return node


def rule(soup):
    hr = soup.new_tag("hr")
    hr["class"] = ["cbm-rule"]
    return hr


def assemble(soup, opts):
    """
    Lift the title and author out, then rebuild the article in the order the
    settings ask for. The body is always present but may be moved; the
    footnotes always come last, because they are generated from the body.
    """
    meta = {"title": "", "author": "", "authors": []}
    author_el = soup.find("p", attrs={"data-role": "author"})
    if author_el is not None:
        meta["author"] = plain(author_el)
    byline, names = (None, [])
    if opts["include"].get("byline"):
        byline, names = build_byline(soup, opts)
    else:
        if author_el is not None:
            author_el.decompose()
    meta["authors"] = names or split_authors(meta["author"])
    title_el = soup.find("p", attrs={"data-role": "title"})
    if title_el is not None:
        meta["title"] = plain(title_el)
        title_el.decompose()

    for role, cls in (("blurb", "cbm-blurb"), ("note", "cbm-note"),
                      ("verse", "cbm-verse")):
        for el in soup.find_all("p", attrs={"data-role": role}):
            el["class"] = [cls]
            del el["data-role"]
    for el in soup.find_all("p", attrs={"data-role": "quote"}):
        el.name = "blockquote"
        del el["data-role"]

    words, minutes = reading_minutes(soup, opts.get("words_per_minute", 200))

    # Collect the movable blocks out of the flow.
    blocks = {}
    blocks["byline"] = [byline] if byline is not None else []
    blocks["blurb"] = [el.extract() for el in soup.find_all("p", class_="cbm-blurb")]
    blocks["note"] = [el.extract() for el in soup.find_all("p", class_="cbm-note")]
    bios = soup.find_all("p", attrs={"data-role": "author_bio"})
    for el in bios:
        el["class"] = ["cbm-bio"]
        del el["data-role"]
    blocks["bio"] = [el.extract() for el in bios]

    read_p = soup.new_tag("p")
    read_p["class"] = ["cbm-read"]
    read_p.append(BeautifulSoup(CLOCK, "html.parser"))
    read_p.append(NavigableString(f"{minutes} min read"))
    blocks["read"] = [read_p]
    blocks["share"] = [share_row(soup, ("cbm-share", "cbm-share-article"))]

    # Whatever is left is the body, with the footnotes pulled off the end.
    footnotes = []
    start = footnote_start(soup)
    if start is not None:
        node = start
        while node is not None:
            nxt = node.next_sibling
            footnotes.append(node.extract())
            node = nxt
    body = [el for el in list(soup.contents)]
    for el in body:
        el.extract()
    blocks["body"] = body

    # Rebuild in order, with a rule wherever the body meets something else.
    order = [b for b in opts["order"] if opts["include"].get(b)]
    for index, name in enumerate(order):
        nodes = blocks.get(name) or []
        if not nodes:
            continue
        previous = order[index - 1] if index else None
        if previous and (previous == "body") != (name == "body"):
            soup.append(rule(soup))
        for node in nodes:
            soup.append(node)
    for node in footnotes:
        soup.append(node)
    return meta, words, minutes


# ------------------------------------------------------------- entry point ---

BLOCK_TAGS_OUT = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
                  "aside", "section", "ol", "ul", "li", "hr", "div")


SVG_CAMEL = ("viewBox", "preserveAspectRatio", "baseProfile",
             "stopColor", "stopOpacity", "gradientUnits")


def restore_svg_case(html):
    """
    HTML parsers lower-case attribute names, but SVG is case-sensitive: a
    browser ignores viewbox and the icon then will not scale. Put the
    capitals back on the way out.
    """
    for name in SVG_CAMEL:
        html = re.sub(r"\b%s=" % name.lower(), name + "=", html)
    return html


def tidy_lines(html):
    """
    Put each block element on its own line. The markup is the same; it is
    simply readable, so anyone maintaining the page can find a paragraph
    without scrolling sideways through one enormous line.
    """
    opening = "|".join(BLOCK_TAGS_OUT)
    html = re.sub(r"(?<!\n)(<(?:%s)[\s>])" % opening, r"\n\1", html)
    html = re.sub(r"(</(?:%s)>)" % opening, r"\1\n", html)
    html = re.sub(r"(<hr[^>]*/?>)", r"\1\n", html)
    html = re.sub(r"[ \t]+\n", "\n", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def convert(path, decide_orphans=None, opts=None):
    """
    Convert one file. decide_orphans(list_of_texts) is called when a pull quote
    matches nothing; return True to proceed without them, False to abandon.
    Returns (html, meta, log) or (None, meta, log) if abandoned.
    """
    path = pathlib.Path(path)
    opts = opts or options()
    log = []
    if path.suffix.lower() == ".docx":
        html, messages, pictures = read_docx(path)
        # The reader gives the picture's bytes; the document itself says how
        # big it is shown and whether text wraps round it. Same order, so
        # they line up.
        for picture, placement in zip(pictures, docx_pictures(path)):
            picture.update({k: v for k, v in placement.items()
                            if k != "alt" or not picture.get("alt")})
        soup = BeautifulSoup(html, "html.parser")
        apply_docx_roles(soup)
        unknown = [m for m in messages if "Unrecognised paragraph style" in m]
        if unknown:
            log.append(f"{len(unknown)} unrecognised Word style(s); those became body text")
    else:
        pictures = []
        html, roles, css_found = read_indesign(path)
        soup = BeautifulSoup(html, "html.parser")
        if soup.body is not None:
            soup = BeautifulSoup(soup.body.decode_contents(), "html.parser")
        log.append("read the InDesign stylesheet" if css_found
                   else "WARNING no stylesheet found; italics may be lost")
        apply_indesign_roles(soup, roles)

    for tag in soup(["script", "style", "link", "meta"]):
        tag.decompose()
    tidy(soup)

    label_front_matter(soup)
    fix_self_links(soup)

    figures, missing_alt = build_figures(soup, pictures)
    quotes = build_pull_quotes(soup)
    moved, orphans = relocate_pull_quotes(soup, quotes)
    if orphans:
        texts = [plain(o.find("p", class_="cbm-pullquote-text")) for o in orphans]
        proceed = decide_orphans(texts) if decide_orphans else True
        if not proceed:
            return None, {}, log + ["abandoned at the operator's request"]
        for o in orphans:
            o.decompose()
        log.append(f"removed {len(orphans)} pull quote(s) that matched no paragraph")
    alternate_sides(soup)

    brackets, nested = tidy_footnote_callouts(soup)
    linked = number_footnotes(soup)
    tabs = outbound_links_new_tab(soup)
    heads = style_headings(soup)
    meta, words, minutes = assemble(soup, opts)
    meta["pictures"] = pictures
    rtl = mark_languages(soup)
    inline_he = tag_inline_hebrew(soup)

    body = restore_svg_case(tidy_lines(soup.decode()))
    body = '<div class="cbm-article">\n' + body.strip() + "\n</div>"
    if soup.find(class_="cbm-share"):
        body = body.rstrip() + "\n" + SHARE_SCRIPT.strip() + "\n"

    changed = non_default(opts)
    settings_note = ("  - settings: " + "; ".join(changed)) if changed else ""
    stamp = (f"<!-- CBM Article Converter {VERSION} - converted "
             f"{datetime.datetime.now():%Y-%m-%d %H:%M} - from: {path.name}"
             f"{settings_note} -->")
    header = ""
    if meta.get("title"):
        header += f"TITLE\n{meta['title']}\n\n"
    if meta.get("author"):
        header += f"AUTHOR\n{meta['author']}\n\n"
    known = {author_slug(n) for n in (opts.get("known_authors") or [])}
    base = (opts.get("profile_base") or PROFILE_BASE).rstrip("/")
    unknown = [n for n in meta.get("authors", []) if author_slug(n) not in known]
    if unknown:
        header += "PROFILE PAGES NEEDED\n"
        header += ("The byline links to these. Make each page at exactly this\n"
                   "address, or the link will be dead.\n")
        for name in unknown:
            header += f"  {name}\n    {base}/{author_slug(name)}\n"
        header += "\n"
    if header:
        header += "----- paste everything below this line into the Code Block -----\n\n"

    log.append(f"{len(quotes)} pull quote(s); {moved} moved into place" if quotes
               else "no pull quotes")
    if figures:
        log.append(f"{len(figures)} picture(s) set aside with a marker in the text")
    if missing_alt:
        log.append("no alt text on: " + ", ".join(missing_alt))
        log.append("   alt text describes a picture to readers using a screen "
                   "reader, and to search engines. Add it in Word: right-click "
                   "the picture, then Alt Text.")
    log.append(f"{linked} footnote number(s) linked back")
    if brackets:
        log.append(f"removed brackets from {brackets} footnote callout(s)")
    if nested:
        log.append(f"unwrapped {nested} doubled superscript(s) in the text")
    log.append(f"headings: " + ", ".join(f"{k} {v}" for k, v in sorted(heads.items())) if heads
               else "no headings found")
    log.append(f"{words} words in the body - {minutes} min read")
    if rtl:
        log.append(f"{rtl} Hebrew paragraph(s) set right to left")
    if inline_he:
        log.append(f"{inline_he} Hebrew word(s) or phrase(s) tagged within English text")
    if tabs:
        log.append(f"{tabs} outbound link(s) open in a new tab")
    return header + stamp + "\n" + body.strip() + "\n", meta, log


def for_checking(html, opts=None, images_dir=None):
    """
    The same article with the stylesheet attached, and the pictures shown
    from the folder beside it, so the .html renders properly when it is
    opened to check. The .txt keeps its markers: on the site the pictures
    are uploaded and the styling comes from Custom CSS.
    """
    opts = opts or options()
    marker = '<div class="cbm-article">'
    if marker not in html:
        return html
    html = html.replace(marker, marker + "\n" + article_css(opts), 1)
    if not images_dir:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for figure in soup.find_all("figure", class_="cbm-figure"):
        slot = figure.find("div", class_="cbm-image-missing")
        name = figure.get("data-cbm-file")
        if slot is None or not name:
            continue
        picture = soup.new_tag("img")
        picture["src"] = f"{images_dir}/{name}"
        picture["alt"] = figure.get("data-cbm-alt", "")
        picture["style"] = "width:100%;height:auto;display:block"
        slot.replace_with(picture)
    return soup.decode()


def images_dir(stem):
    """The folder the pictures go in, beside the article."""
    return f"{stem}-pictures"


def write_outputs(source, html, opts=None, pictures=()):
    """Write .html and .txt, stamped with the time. Beside the original by
    default, or into a folder chosen in the settings."""
    opts = opts or options()
    source = pathlib.Path(source)
    folder = source.parent
    if opts.get("output") == "folder" and opts.get("output_folder"):
        candidate = pathlib.Path(opts["output_folder"])
        if candidate.is_dir():
            folder = candidate
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    base = re.sub(r"^\d{8}_\d{4}_", "", source.stem)
    out_html = folder / f"{stamp}_{base}.html"
    out_txt = folder / f"{stamp}_{base}.txt"
    # Always Windows line endings, whichever machine converted the file.
    # Otherwise an article converted on a Mac arrives as one long line in
    # Notepad, and the two tracks produce visibly different files.
    def windows_lines(text):
        return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    out_html.write_bytes(windows_lines(for_checking(html, opts, images_dir=images_dir(base))))
    out_txt.write_bytes(windows_lines(html))

    written = []
    if pictures:
        folder = out_html.parent / images_dir(base)
        folder.mkdir(exist_ok=True)
        for picture in pictures:
            target = folder / picture["name"]
            target.write_bytes(picture["data"])
            written.append(target)
    return out_html, out_txt, written


# ------------------------------------------------- adding styles to a file ---

# The styles an editor actually applies. Left/Right Side Bar are optional:
# pull quotes alternate sides on their own, and these only pin one to a side.
# First Paragraph is deliberately absent - it existed for Pandoc's benefit and
# nothing emits it now.
HOUSE_STYLE_WANTED = [
    "Author Bio", "Blurb", "Side Bar", "Verse Block", "Article Note",
    "Block Text", "Body Text",
]
HOUSE_STYLE_OPTIONAL = ["Left Side Bar", "Right Side Bar"]


def _styles_xml(path):
    with zipfile.ZipFile(path) as z:
        return z.read("word/styles.xml").decode("utf-8")


def _style_blocks(xml):
    """styleId -> (name, xml) for every style defined in a styles.xml."""
    out = {}
    for m in re.finditer(r"<w:style\b[^>]*>.*?</w:style>", xml, re.S):
        block = m.group(0)
        sid = re.search(r'w:styleId="([^"]+)"', block)
        nm = re.search(r'<w:name w:val="([^"]+)"', block)
        if sid:
            out[sid.group(1)] = (nm.group(1) if nm else sid.group(1), block)
    return out


def _needed_with_parents(wanted_ids, source):
    """Include whatever a wanted style is based on, and its linked character style."""
    needed, queue = [], list(wanted_ids)
    while queue:
        sid = queue.pop(0)
        if sid in needed or sid not in source:
            continue
        needed.append(sid)
        block = source[sid][1]
        for pat in (r'<w:basedOn w:val="([^"]+)"', r'<w:link w:val="([^"]+)"',
                    r'<w:next w:val="([^"]+)"'):
            for ref in re.findall(pat, block):
                if ref in source and ref not in needed:
                    queue.append(ref)
    return needed


def add_house_styles(manuscript, template, out_path=None):
    """
    Copy the house styles from the template into a copy of the manuscript.
    Nothing in the document is rewritten: only style definitions are added,
    so comments, tables and tracked changes are untouched.
    Returns (output path, added names, already present names).
    """
    manuscript, template = pathlib.Path(manuscript), pathlib.Path(template)
    src = _style_blocks(_styles_xml(template))
    dst_xml = _styles_xml(manuscript)
    dst = _style_blocks(dst_xml)

    wanted_ids, skipped = [], []
    for sid, (name, _block) in src.items():
        if any(w.lower() == name.lower()
               for w in HOUSE_STYLE_WANTED + HOUSE_STYLE_OPTIONAL):
            if any(d_name.lower() == name.lower() for d_name, _ in dst.values()):
                skipped.append(name)
            else:
                wanted_ids.append(sid)

    needed = [sid for sid in _needed_with_parents(wanted_ids, src) if sid not in dst]
    added = []
    additions = []
    for sid in needed:
        name, block = src[sid]
        # make sure it shows in Word's style gallery rather than hiding
        block = re.sub(r"\s*<w:semiHidden\s*/>", "", block)
        block = re.sub(r"\s*<w:unhideWhenUsed\s*/>", "", block)
        if "<w:qFormat" not in block:
            block = block.replace("</w:style>", "<w:qFormat/></w:style>")
        additions.append(block)
        added.append(name)

    if not additions:
        return None, [], skipped

    new_xml = dst_xml.replace("</w:styles>", "".join(additions) + "</w:styles>")
    if out_path is None:
        out_path = manuscript.with_name(manuscript.stem + " (house styles).docx")
    out_path = pathlib.Path(out_path)

    with zipfile.ZipFile(manuscript) as zin, \
         zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                data = new_xml.encode("utf-8")
            zout.writestr(item, data)
    return out_path, added, skipped


# -------------------------------------------------------------- settings ----

SETTINGS_FILE = pathlib.Path.home() / ".cbm-article-converter.json"


def load_settings():
    import json
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data):
    import json
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def remembered_template():
    """The template used last time, if it is still where it was."""
    path = load_settings().get("template")
    if path and pathlib.Path(path).exists():
        return pathlib.Path(path)
    return None


def remember_template(path):
    data = load_settings()
    data["template"] = str(pathlib.Path(path))
    save_settings(data)


def running_from_temp():
    """
    True when loose source files were launched from inside a zip, which cannot
    work because the other files are not really there.

    A built application is exempt. PyInstaller unpacks a one-file executable
    into a temporary folder and runs from there, so the test would otherwise
    fire every single time.
    """
    import sys, tempfile
    if getattr(sys, "frozen", False):
        return False
    try:
        here = pathlib.Path(__file__).resolve().parent
    except NameError:
        return False
    temp = pathlib.Path(tempfile.gettempdir()).resolve()
    try:
        here.relative_to(temp)
        return True
    except ValueError:
        pass
    return bool(re.match(r"(?i)^Temp\d*_", here.name))


# ---------------------------------------------------------- updates ---------

GITHUB_OWNER = "RexBHavgreau"
GITHUB_REPO = "cbm-squarespace-tool"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"


VERSION_EXACT = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
VERSION_ANYWHERE = re.compile(r"\bv?(\d+)\.(\d+)(?:\.(\d+))?\b")


def version_tuple(text, anywhere=False):
    """
    'v1.2.10' -> (1, 2, 10). Compared as numbers, so 1.10 beats 1.9.

    A dotted number is required, so an old tag such as "build49" returns
    nothing and cannot masquerade as a release far ahead of this one.
    With anywhere=True the number may sit inside a longer string, which is
    how a release TITLE such as "Version 1.0.1" is read.
    """
    text = str(text or "").strip()
    m = VERSION_EXACT.match(text)
    if not m and anywhere:
        m = VERSION_ANYWHERE.search(text)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def platform_asset(assets):
    """
    Pick the download meant for this machine, or nothing.

    Nothing is the right answer when a release carries no file for this
    platform. Falling back to whatever was attached first would hand a Mac
    user a Windows executable, which is worse than saying there is none.
    """
    import sys
    if sys.platform.startswith("win"):
        wanted, avoid = (".exe", "windows", "win"), ("mac", "darwin", ".dmg")
    elif sys.platform == "darwin":
        wanted, avoid = ("mac", "darwin", ".dmg", ".app"), (".exe", "windows")
    else:
        wanted, avoid = ("linux", ".tar"), (".exe", ".dmg", "mac", "windows")
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if any(a in name for a in avoid):
            continue
        if any(w in name for w in wanted):
            return asset
    return None


def check_for_update(timeout=10):
    """
    Ask GitHub for the newest release.

    Returns a dict when something newer exists, None when up to date, and
    raises nothing the caller has to handle beyond UpdateError.
    """
    import json
    import urllib.request
    request = urllib.request.Request(
        RELEASES_API,
        headers={"User-Agent": f"CBM-Article-Converter/{VERSION}",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        raise UpdateError(describe_network_error(exc)) from exc

    # The version may be on the tag or in the release title. The tag is the
    # better home for it, but a title like "Version 1.0.1" is read too, so a
    # release named one way and tagged another still works.
    tag = data.get("tag_name") or ""
    title = data.get("name") or ""
    there = version_tuple(tag)
    latest = tag
    if there is None:
        there = version_tuple(title, anywhere=True)
        latest = title
    here = version_tuple(VERSION)
    if there is None:
        raise UpdateError(
            f"The newest release is tagged \u201c{tag}\u201d and titled "
            f"\u201c{title}\u201d, and neither contains a version number like "
            "1.0.1, so there is no way to tell whether it is newer.")
    if here is None or there <= here:
        return None
    asset = platform_asset(data.get("assets") or [])
    return {
        # Built from the numbers themselves. Trimming letters off the front of
        # the tag or title is not safe: "Version 1.1.0" would lose its V.
        "version": "%d.%d.%d" % there,
        "notes": (data.get("body") or "").strip(),
        "page": data.get("html_url") or RELEASES_PAGE,
        "asset_name": asset.get("name") if asset else None,
        "asset_url": asset.get("browser_download_url") if asset else None,
        "asset_size": asset.get("size") if asset else 0,
    }


def download_update(url, folder, name, timeout=60):
    """Save a release file into a folder of the user's choosing."""
    import urllib.request
    folder = pathlib.Path(folder)
    target = folder / name
    request = urllib.request.Request(
        url, headers={"User-Agent": f"CBM-Article-Converter/{VERSION}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except Exception as exc:                                   # noqa: BLE001
        raise UpdateError(describe_network_error(exc)) from exc
    target.write_bytes(data)
    return target


class UpdateError(Exception):
    pass


def describe_network_error(exc):
    """Say what went wrong in terms the person running this can act on."""
    text = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text.upper():
        return ("The secure connection could not be verified. This sometimes "
                "happens on a managed network. Download the new version from "
                f"{RELEASES_PAGE} instead.")
    if "403" in text and "rate" in text.lower():
        return ("GitHub is briefly refusing requests from this network because "
                "too many have been made in the last hour. Try again later, or "
                f"go to {RELEASES_PAGE}.")
    if "404" in text:
        return ("No releases have been published yet, or the address has "
                "changed.")
    if "timed out" in text.lower() or "urlopen error" in text.lower():
        return ("Could not reach GitHub. Check the internet connection, or go "
                f"to {RELEASES_PAGE}.")
    return f"Could not check for updates: {text}"


# ------------------------------------------------------------ documents ----

DOCUMENTS = [
    ("User guide", "USER-GUIDE.txt"),
    ("What the HTML looks like", "HTML-REFERENCE.txt"),
    ("Building the app", "BUILD-NOTES.txt"),
]


def resource_dir():
    """
    Where the bundled files live. PyInstaller unpacks them to a temporary
    folder and points sys._MEIPASS at it; running from source they sit
    beside this file.
    """
    import sys
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return pathlib.Path(bundled)
    return pathlib.Path(__file__).resolve().parent


def document_path(filename):
    """The bundled copy of a document, or None if it is not there."""
    candidate = resource_dir() / filename
    return candidate if candidate.exists() else None


def open_document(filename):
    """
    Open a bundled document in whatever the system uses for text files.
    Copied out to a stable place first: inside a packaged app the bundled
    copy lives in a temporary folder that disappears when the app closes,
    which would shut the reader's window with it.
    """
    import os
    import subprocess
    import sys
    source = document_path(filename)
    if source is None:
        raise FileNotFoundError(filename)
    home = pathlib.Path.home() / ".cbm-article-converter-docs"
    home.mkdir(exist_ok=True)
    target = home / filename
    target.write_bytes(source.read_bytes())
    if sys.platform.startswith("win"):
        os.startfile(str(target))                        # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return target


# ------------------------------------------------------------- shortcuts ---
# Windows calls them shortcuts and stores them as .lnk files; macOS calls the
# same idea an alias. Both are made through the system rather than by writing
# a file, so each needs its own small incantation.

SHORTCUT_STEM = "CBM Article Converter"


def desktop_path():
    for candidate in (pathlib.Path.home() / "Desktop",
                      pathlib.Path.home() / "OneDrive" / "Desktop"):
        if candidate.is_dir():
            return candidate
    return None


def existing_shortcuts():
    """Shortcuts to any version of this app sitting on the Desktop."""
    import sys
    desktop = desktop_path()
    if desktop is None:
        return []
    found = []
    for item in desktop.iterdir():
        name = item.name
        if not name.startswith(SHORTCUT_STEM):
            continue
        if sys.platform.startswith("win"):
            if item.suffix.lower() == ".lnk":
                found.append(item)
        elif item.is_symlink() or item.suffix == "":
            found.append(item)
    return sorted(found)


def shortcut_name(target):
    """A shortcut named for the version it points at."""
    import sys
    stem = pathlib.Path(target).stem
    return stem + (".lnk" if sys.platform.startswith("win") else "")


def make_shortcut(target, replace=()):
    """
    Put a shortcut to this version on the Desktop, optionally clearing older
    ones away first. Returns the shortcut's path.
    """
    import subprocess
    import sys
    import sys as _sys
    target = pathlib.Path(target).resolve()
    # Check the target before the Desktop, so the more useful complaint wins.
    if _sys.platform == "darwin" and target.suffix != ".app":
        raise ShortcutError(
            "An alias can only point at the app itself. Expand the downloaded "
            "zip first, then use Preferences \u203a Desktop shortcut.")
    if not target.exists():
        raise ShortcutError(f"{target.name} is not where it was expected.")
    desktop = desktop_path()
    if desktop is None:
        raise ShortcutError("Could not find the Desktop folder.")

    link = desktop / shortcut_name(target)
    if sys.platform.startswith("win"):
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut("
            f"'{link}'); $s.TargetPath = '{target}'; "
            f"$s.WorkingDirectory = '{target.parent}'; "
            "$s.Description = 'CBM Article Converter'; $s.Save()")
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True)
        if done.returncode != 0:
            raise ShortcutError((done.stderr or "").strip()[:200]
                                or "Windows refused to make the shortcut.")
    elif sys.platform == "darwin":
        script = (f'tell application "Finder" to make alias file to '
                  f'POSIX file "{target}" at POSIX file "{desktop}"')
        done = subprocess.run(["osascript", "-e", script],
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise ShortcutError((done.stderr or "").strip()[:200]
                                or "Finder refused to make the alias.")
    else:
        raise ShortcutError("Shortcuts are only made on Windows and macOS.")

    for old in replace:
        old = pathlib.Path(old)
        if old.exists() and old.resolve() != link.resolve():
            try:
                old.unlink()
            except OSError:
                pass
    return link


class ShortcutError(Exception):
    pass


def app_folder():
    """
    Where this copy of the app lives, which is where a new version should
    land beside it. For a packaged app that is the folder holding the
    executable, not the temporary place PyInstaller unpacks into.
    """
    import sys
    if getattr(sys, "frozen", False):
        here = pathlib.Path(sys.executable).resolve().parent
    else:
        here = pathlib.Path(__file__).resolve().parent
    # A protected location would only fail at the moment of writing.
    probe = here / ".cbm-write-test"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return here
    except OSError:
        return pathlib.Path.home() / "Downloads" if (
            pathlib.Path.home() / "Downloads").is_dir() else pathlib.Path.home()


# ----------------------------------------------------- article link cards ---

CARD_CSS = """<style>
.cbm-cards { margin:2em 0; }
.cbm-cards .cbm-card {
  display:grid; grid-template-columns:1fr; gap:0.9em; padding:1.6em 0;
  border-top:1px solid color-mix(in srgb, currentColor 22%, transparent);
}
.cbm-cards .cbm-card:last-child {
  border-bottom:1px solid color-mix(in srgb, currentColor 22%, transparent);
}
.cbm-cards img { width:100%; height:auto; display:block; aspect-ratio:3/2; object-fit:cover; }
.cbm-cards h3 { margin:0 0 0.3em; font-size:1.15em; line-height:1.3; }
.cbm-cards h3 a { color:inherit; text-decoration:none; }
.cbm-cards h3 a:hover { text-decoration:underline; }
.cbm-cards .cbm-card-date {
  margin:0 0 0.5em; font-size:0.75em; letter-spacing:0.08em;
  text-transform:uppercase; opacity:0.7;
}
.cbm-cards .cbm-card-excerpt { margin:0; opacity:0.85; }
@media (min-width:46em) {
  .cbm-cards .cbm-card {
    grid-template-columns:15em 1fr; gap:1.6em; align-items:start;
  }
}
</style>"""


def fetch_article(url, timeout=15):
    """
    Read one article's details straight from the site, so nobody has to
    transcribe a thumbnail address. Returns what it found; anything missing
    comes back empty for the operator to fill in.
    """
    import json
    import urllib.parse
    import urllib.request
    url = url.strip()
    if not url:
        raise UpdateError("No address given.")
    parts = urllib.parse.urlsplit(url if "://" in url else "https://" + url)
    collection = parts.path.rsplit("/", 1)[0] or "/articles"
    slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
    feed = urllib.parse.urlunsplit(
        (parts.scheme or "https", parts.netloc, collection, "format=json", ""))
    request = urllib.request.Request(
        feed, headers={"User-Agent": f"CBM-Article-Converter/{VERSION}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        raise UpdateError(describe_network_error(exc)) from exc
    for item in data.get("items") or []:
        if item.get("urlId") == slug or slug in str(item.get("fullUrl", "")):
            published = item.get("publishOn")
            when = ""
            if published:
                when = datetime.datetime.fromtimestamp(
                    published / 1000, datetime.timezone.utc).strftime("%d %B %Y")
            excerpt = re.sub(r"<[^>]+>", "", item.get("excerpt") or "").strip()
            return {
                "title": (item.get("title") or "").strip(),
                "url": item.get("fullUrl") or parts.path,
                "date": when,
                "excerpt": re.sub(r"\s+", " ", excerpt),
                "image": item.get("assetUrl") or "",
            }
    raise UpdateError(
        "That article was not in the first page of the collection. Paste the "
        "details by hand, or try an article published more recently.")


def article_card(entry, with_style=True):
    """One card, ready to paste. Repeat the inner div for more articles."""
    from html import escape
    title = escape(entry.get("title") or "")
    url = escape(entry.get("url") or "")
    date = escape(entry.get("date") or "")
    excerpt = escape(entry.get("excerpt") or "")
    image = entry.get("image") or ""
    if image and "?" not in image:
        image += "?format=600w"
    picture = (f'  <a href="{url}"><img src="{escape(image)}" alt="" loading="lazy" /></a>\n'
               if image else "")
    card = (f'<div class="cbm-card">\n{picture}'
            f'  <div>\n'
            + (f'    <p class="cbm-card-date">{date}</p>\n' if date else "")
            + f'    <h3><a href="{url}">{title}</a></h3>\n'
            + (f'    <p class="cbm-card-excerpt">{excerpt}</p>\n' if excerpt else "")
            + '  </div>\n</div>')
    if not with_style:
        return card
    return '<div class="cbm-cards">\n' + CARD_CSS + "\n\n" + card + "\n</div>"


SAMPLE_BODY = """<p class="cbm-byline">By <a href="/profile/chris-burnett">Chris Burnett</a> and <a href="/profile/scott-callaham">Scott Callaham</a></p>
<p class="cbm-blurb">Russian evangelicalism developed under the influence of Orthodoxy rather than the Reformation.</p>
<p class="cbm-note">This is the second in a series.</p>
<p class="cbm-read">__CLOCK__27 min read</p>
<hr class="cbm-rule" />
<h2>Baptism and the Gospel</h2>
<aside class="cbm-pullquote cbm-pq-left"><p class="cbm-pullquote-text">Baptism is not the final step of salvation.</p><p class="cbm-share">__SHARE__</p></aside>
<p>Second, baptism is not the final step of salvation. If it were, the thief on the cross could have had no hope, and Paul would not have thanked God that he baptised so few at Corinth. The Reformers returned to this point repeatedly, because the alternative makes the sacrament the thing that saves.<sup><a href="#s-fn1" id="s-ref1">1</a></sup></p>
<p>The quotes alternate down the article: the first sits left, the next right. That is worked out in reading order.</p>
<h4>A lesser heading</h4>
<p class="cbm-verse">The LORD is my shepherd;<br/>I shall not want.</p>
<blockquote><p>We do not become members of Christ\u2019s body by the act of baptism.</p></blockquote>
<p class="cbm-share cbm-share-article">__SHARE__</p>
<hr class="cbm-rule" />
<p class="cbm-bio">Alex is the dean and New Testament Chair at Samara Center for Biblical Training.</p>
<section class="footnotes"><ol class="cbm-footnotes"><li id="s-fn1"><p><a href="#s-ref1" class="footnote-back">1.</a>&#160;See Jonathan H. Rainbow, <em>Confessor Baptism</em>, 189\u201392.</p></li></ol></section>"""


def sample_article(opts=None):
    """A complete little article, for seeing the styles at work."""
    share = "".join(
        f'<a href="#" title="Share">{ICONS[k]}</a>' for k in ("x", "fb", "email"))
    body = SAMPLE_BODY.replace("__CLOCK__", CLOCK).replace("__SHARE__", share)
    body = restore_svg_case(body)
    return ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Style preview</title><style>"
            "body{margin:0;background:#fbfbf9;color:#1b1b1a;"
            "font-family:Georgia,serif;line-height:1.65;}"
            ".page{max-width:44em;margin:3em auto;padding:0 1.5em;}"
            "@media(prefers-color-scheme:dark){body{background:#17171a;color:#eceae4}}"
            "</style></head><body><div class=\"page\">"
            + article_css(opts) + '<div class="cbm-article">' + body
            + "</div></div></body></html>")


# --------------------------------------------------------------- pictures ---
# Word records how big a picture is shown and whether text wraps around it.
# Reading that means the editor sizes and places a photograph in Word, the
# way they always have, and the article follows.

EMU_PER_INCH = 914400


def _text_column_inches(xml):
    """The width of the text column, for turning a picture's width into a share
    of it. Falls back to a typical 6.5in if the section is not described."""
    page = re.search(r'<w:pgSz\b[^>]*w:w="(\d+)"', xml)
    margins = re.search(r'<w:pgMar\b[^>]*>', xml)
    if not page:
        return 6.5
    width = int(page.group(1)) / 1440.0          # twentieths of a point
    left = right = 1.0
    if margins:
        ml = re.search(r'w:left="(\d+)"', margins.group(0))
        mr = re.search(r'w:right="(\d+)"', margins.group(0))
        if ml:
            left = int(ml.group(1)) / 1440.0
        if mr:
            right = int(mr.group(1)) / 1440.0
    return max(1.0, width - left - right)


def docx_pictures(path):
    """
    Every picture in the document, in order, with how Word shows it.

    side is "left", "right" or None; None means it sits in the text flow at
    full width rather than having text wrapped around it.
    """
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return []
    column = _text_column_inches(xml)
    found = []
    for m in re.finditer(r"<w:drawing>.*?</w:drawing>", xml, re.S):
        frag = m.group(0)
        extent = re.search(r'<wp:extent\b[^>]*cx="(\d+)"[^>]*cy="(\d+)"', frag)
        width_in = int(extent.group(1)) / EMU_PER_INCH if extent else column
        height_in = int(extent.group(2)) / EMU_PER_INCH if extent else 0
        alt = ""
        doc_pr = re.search(r"<wp:docPr\b[^>]*>", frag)
        if doc_pr:
            descr = re.search(r'descr="([^"]*)"', doc_pr.group(0))
            if descr:
                alt = descr.group(1).strip()
        side = None
        if "<wp:anchor" in frag and not re.search(r"<wp:wrapNone\b", frag):
            if re.search(r"<wp:wrap(Square|Tight|Through)\b", frag):
                align = re.search(r"<wp:align>(left|right)</wp:align>", frag)
                side = align.group(1) if align else "left"
        share = max(10, min(100, round(100.0 * width_in / column)))
        found.append({
            "width_in": round(width_in, 2),
            "height_in": round(height_in, 2),
            "percent": share,
            "side": side,
            "alt": alt,
        })
    return found


def pictures_awaiting(html):
    """Every picture marker in an article, in order."""
    soup = BeautifulSoup(html, "html.parser")
    waiting = []
    for figure in soup.find_all("figure", class_="cbm-figure"):
        if figure.find("div", class_="cbm-image-missing") is None:
            continue
        waiting.append({
            "file": figure.get("data-cbm-file", ""),
            "alt": figure.get("data-cbm-alt", ""),
        })
    return waiting


def place_pictures(html, addresses, widths=(600, 1000, 1600)):
    """
    Replace each marker with the real picture, once it has been uploaded and
    has an address. addresses maps a file name to its address.

    Squarespace resizes on request, so a set of widths is offered and the
    browser takes whichever suits the reader's screen.
    """
    soup = BeautifulSoup(html, "html.parser")
    placed, left = 0, 0
    for figure in soup.find_all("figure", class_="cbm-figure"):
        slot = figure.find("div", class_="cbm-image-missing")
        if slot is None:
            continue
        name = figure.get("data-cbm-file", "")
        address = (addresses.get(name) or "").strip()
        if not address:
            left += 1
            continue
        picture = soup.new_tag("img")
        picture["src"] = address
        picture["alt"] = figure.get("data-cbm-alt", "")
        picture["loading"] = "lazy"
        if "squarespace" in address and "?" not in address:
            picture["srcset"] = ", ".join(
                f"{address}?format={w}w {w}w" for w in widths)
            picture["sizes"] = "(min-width: 700px) 50vw, 100vw"
        slot.replace_with(picture)
        placed += 1
    return restore_svg_case(tidy_lines(soup.decode())), placed, left
