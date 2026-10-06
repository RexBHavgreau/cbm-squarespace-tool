"""
CBM Article Converter - conversion core.
Version 1.0.0
"""
import re, math, copy, datetime, pathlib, zipfile
import mammoth
from bs4 import BeautifulSoup, Tag, NavigableString

VERSION = "1.2.0"

# Kept so anything that still asks for a build number gets something sensible.
BUILD = VERSION
WORDS_PER_MINUTE = 200

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
ARTICLE_CSS = """<style>
.cbm-article .cbm-blurb { font-size:1.15em; line-height:1.5; }
.cbm-article .cbm-note { font-style:italic; }
.cbm-article .cbm-clock {
  width:1em; height:1em; vertical-align:-0.13em; margin-right:0.45em;
}
.cbm-article .cbm-read {
  text-align:center; font-size:0.78em;
  letter-spacing:0.09em; text-transform:uppercase;
}
.cbm-article .cbm-rule {
  border:none; border-top:1px solid currentColor;
  opacity:0.25; margin:1.6em 0;
}
.cbm-article h2, .cbm-article h3 { text-align:center; }
.cbm-article h4 { text-align:left; font-style:italic; }
.cbm-article .cbm-verse { margin-left:2.5em; text-indent:-1.25em; }
.cbm-article .cbm-bio {
  text-align:center; font-style:italic; font-size:0.9em;
}
.cbm-article [lang="he"] { text-align:right; }
.cbm-article .cbm-verse[lang="he"] { margin-left:0; margin-right:2.5em; }

.cbm-article .cbm-pullquote {
  max-width:32em; margin:2em auto; padding:0.8em 0;
  border-top:1px solid currentColor; border-bottom:1px solid currentColor;
  text-align:center;
}
.cbm-article .cbm-pullquote-text {
  margin:0 0 0.5em; font-style:italic; font-size:1.25em; line-height:1.4;
}
.cbm-article .cbm-share { margin:0; line-height:1; }
.cbm-article .cbm-share a {
  display:inline-block; margin:0 0.45em; color:currentColor;
  text-decoration:none; opacity:0.75;
}
.cbm-article .cbm-share a:hover { opacity:1; }
.cbm-article .cbm-share svg { width:1.15em; height:1.15em; vertical-align:middle; }

/* Floated into the margin on a wide screen, alternating down the page.
   Below this width they stay as centred blocks: a narrow floating box
   is unreadable. */
@media (min-width: 900px) {
  .cbm-article .cbm-pullquote {
    width:38%; max-width:none; margin:0.4em 0 1em 0; text-align:left;
  }
  .cbm-article .cbm-pq-left {
    float:left; margin-left:-0.75in; margin-right:1.6em;
  }
  .cbm-article .cbm-pq-right {
    float:right; margin-right:-0.75in; margin-left:1.6em;
  }
}

/* Keep the footnotes and the bio clear of any floated quote above them. */
.cbm-article .cbm-footnotes { list-style:none; padding-left:0; }
.cbm-article .footnote-back { text-decoration:none; font-weight:600; }

/* Keep the footnotes and the bio clear of any floated quote above them. */
.cbm-article .cbm-rule, .cbm-article .cbm-footnotes,
.cbm-article section { clear:both; }
</style>"""

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
  var url = encodeURIComponent(window.location.href);
  var boxes = document.querySelectorAll('.cbm-pullquote');
  for (var i = 0; i < boxes.length; i++) {
    var q = boxes[i].querySelector('.cbm-pullquote-text');
    if (!q) continue;
    var text = encodeURIComponent('\\u201c' + q.textContent.trim() + '\\u201d');
    var x = boxes[i].querySelector('.cbm-share-x');
    var f = boxes[i].querySelector('.cbm-share-fb');
    var e = boxes[i].querySelector('.cbm-share-email');
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
    """Word -> HTML, with house styles mapped to marker elements."""
    rules = [f"p[style-name='Heading {i}'] => h{i}:fresh" for i in range(1, 7)]
    seen = set()
    for style in docx_style_names(path):
        role = role_of(style)
        if role and "'" not in style:
            rules.append(f"p[style-name='{style}'] => div.cbm-{role}:fresh")
            seen.add(role)
    with open(path, "rb") as fh:
        result = mammoth.convert_to_html(fh, style_map="\n".join(rules))
    return result.value, [str(m) for m in result.messages]


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
        share = soup.new_tag("p")
        share["class"] = ["cbm-share"]
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
            share.append(a)
        aside.append(share)
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

def reading_minutes(soup):
    clone = BeautifulSoup(str(soup), "html.parser")
    for el in clone.find_all(["aside", "section"]):
        el.decompose()
    for el in clone.find_all("p", attrs={"data-role": True}):
        el.decompose()
    for el in clone.find_all("ol"):
        if el.find("li", id=re.compile(r"(fn\d|footnote)")):
            el.decompose()
    words = [w for w in re.split(r"\s+", clone.get_text(" ")) if re.search(r"\w", w)]
    return len(words), max(1, math.ceil(len(words) / WORDS_PER_MINUTE)) if words else 0


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


def assemble(soup):
    """Front matter at the top, bio at the end, title and author lifted out."""
    meta = {"title": "", "author": ""}
    for role in ("title", "author"):
        el = soup.find("p", attrs={"data-role": role})
        if el is not None:
            meta[role] = plain(el)
            el.decompose()

    for el in soup.find_all("p", attrs={"data-role": "blurb"}):
        el["class"] = ["cbm-blurb"]
        del el["data-role"]
    for el in soup.find_all("p", attrs={"data-role": "note"}):
        el["class"] = ["cbm-note"]
        del el["data-role"]
    for el in soup.find_all("p", attrs={"data-role": "verse"}):
        el["class"] = ["cbm-verse"]
        del el["data-role"]
    for el in soup.find_all("p", attrs={"data-role": "quote"}):
        el.name = "blockquote"
        del el["data-role"]

    words, minutes = reading_minutes(soup)

    bios = soup.find_all("p", attrs={"data-role": "author_bio"})
    bio_nodes = []
    for el in bios:
        el["class"] = ["cbm-bio"]
        del el["data-role"]
        bio_nodes.append(el.extract())

    # reading time after the blurb, else before the first heading
    read_p = soup.new_tag("p")
    read_p["class"] = ["cbm-read"]
    read_p.append(BeautifulSoup(CLOCK, "html.parser"))
    read_p.append(NavigableString(f"{minutes} min read"))
    anchor = soup.find("p", class_="cbm-blurb")
    if anchor is not None:
        anchor.insert_after(read_p)
        read_p.insert_after(rule(soup))
    else:
        first_head = soup.find(["h1", "h2", "h3", "h4"])
        if first_head is not None:
            first_head.insert_before(read_p)
            read_p.insert_after(rule(soup))

    # bio at the end, above the footnotes, behind a matching rule
    if bio_nodes:
        start = footnote_start(soup)
        block = [rule(soup)] + bio_nodes
        if start is not None:
            for node in block:
                start.insert_before(node)
        else:
            for node in block:
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


def convert(path, decide_orphans=None):
    """
    Convert one file. decide_orphans(list_of_texts) is called when a pull quote
    matches nothing; return True to proceed without them, False to abandon.
    Returns (html, meta, log) or (None, meta, log) if abandoned.
    """
    path = pathlib.Path(path)
    log = []
    if path.suffix.lower() == ".docx":
        html, messages = read_docx(path)
        soup = BeautifulSoup(html, "html.parser")
        apply_docx_roles(soup)
        unknown = [m for m in messages if "Unrecognised paragraph style" in m]
        if unknown:
            log.append(f"{len(unknown)} unrecognised Word style(s); those became body text")
    else:
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

    linked = number_footnotes(soup)
    tabs = outbound_links_new_tab(soup)
    heads = style_headings(soup)
    meta, words, minutes = assemble(soup)
    rtl = mark_languages(soup)

    body = restore_svg_case(tidy_lines(soup.decode()))
    body = ('<div class="cbm-article">\n' + ARTICLE_CSS + "\n\n"
            + body.strip() + "\n</div>")
    if soup.find("aside", class_="cbm-pullquote"):
        body = body.rstrip() + "\n" + SHARE_SCRIPT.strip() + "\n"

    stamp = (f"<!-- CBM Article Converter {VERSION} - converted "
             f"{datetime.datetime.now():%Y-%m-%d %H:%M} - from: {path.name} -->")
    header = ""
    if meta.get("title"):
        header += f"TITLE\n{meta['title']}\n\n"
    if meta.get("author"):
        header += f"AUTHOR\n{meta['author']}\n\n"
    if header:
        header += "----- paste everything below this line into the Code Block -----\n\n"

    log.append(f"{len(quotes)} pull quote(s); {moved} moved into place" if quotes
               else "no pull quotes")
    log.append(f"{linked} footnote number(s) linked back")
    log.append(f"headings: " + ", ".join(f"{k} {v}" for k, v in sorted(heads.items())) if heads
               else "no headings found")
    log.append(f"{words} words in the body - {minutes} min read")
    if rtl:
        log.append(f"{rtl} Hebrew paragraph(s) set right to left")
    if tabs:
        log.append(f"{tabs} outbound link(s) open in a new tab")
    return header + stamp + "\n" + body.strip() + "\n", meta, log


def write_outputs(source, html):
    """Write .html and .txt beside the original, stamped with the time."""
    source = pathlib.Path(source)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    base = re.sub(r"^\d{8}_\d{4}_", "", source.stem)
    out_html = source.parent / f"{stamp}_{base}.html"
    out_txt = source.parent / f"{stamp}_{base}.txt"
    # Always Windows line endings, whichever machine converted the file.
    # Otherwise an article converted on a Mac arrives as one long line in
    # Notepad, and the two tracks produce visibly different files.
    data = html.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    out_html.write_bytes(data)
    out_txt.write_bytes(data)
    return out_html, out_txt


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
