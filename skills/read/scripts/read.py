#!/usr/bin/env python3
"""read.py: get the text out of a book, paper, article or document so it can be learned.

    read.py open <file or link>      split it into chapters (long) or one text (short), in the working folder
    read.py status                   what is ready and where the library is

Works on: EPUB and PDF books that open freely (no DRM), papers and reports as PDF, web articles, and
.docx, .txt, .md and .html files. Locked books (Kindle, Audible, Adobe DRM) and scans with no text are
refused, never unlocked.

Each source lands in <library>/_working/<id>/: source.md for a short one, chapters/NN.md for a long one,
with a meta.json beside it. library.py turns them into notes and deletes them. Nothing is uploaded; the only
network use is fetching a link the person gave and, once, the PDF reader (pypdf) from PyPI.
"""
from __future__ import annotations

import argparse
import html
import html.parser
import json
import logging
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library import fetch_url, is_local, learned_sources, library, log, make_id, working  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CACHE = Path(os.environ.get("LEARNING_SKILLS_CACHE") or Path.home() / ".cache" / "learning-skills")
# pypdf 7 needs Python 3.10; 6.21.4 is the last release that runs on 3.9 (the Python that comes with macOS).
PYPDF = "pypdf==7.1.0" if sys.version_info >= (3, 10) else "pypdf==6.21.4"
LOCKED_EXT = {".azw": "a Kindle book", ".azw3": "a Kindle book", ".kfx": "a Kindle book", ".mobi": "a Kindle book",
              ".aax": "an Audible book", ".aaxc": "an Audible book", ".acsm": "an Adobe library loan",
              ".lcpl": "a library loan"}
AUDIO_EXT = {".mp3", ".m4a", ".m4b", ".wav", ".ogg", ".flac", ".aac", ".opus"}
TEXT_EXT = {".txt", ".md", ".markdown"}
HTML_EXT = {".html", ".htm", ".xhtml"}
ONE_TEXT_LIMIT = 20_000   # words; anything longer is split into chapters
PAGES_PER_PART = 20       # for a long PDF with no table of contents
MIN_ARTICLE_WORDS = 150
# Chapters that are publisher or reference pages, flagged so the reader can skip them.
SKIP_TITLES = re.compile(r"^(imprint|colophon|uncopyright|copyright|license|licence|about the (author|publisher)|"
                         r"also by|by the same author|dedication|title page|half title|contents|table of contents|index|"
                         r"acknowledg(e)?ments?|front matter|endnotes?|footnotes?|other notes|praise for)\b", re.I)


def words(text: str) -> int:
    return len(text.split())


def tidy(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


# ---------------------------------------------------------------- HTML to text

class TextOut(html.parser.HTMLParser):
    """(X)HTML to plain text with headings and paragraphs. For a web page, keeps only the article when the
    page marks one, and drops navigation, headers, footers, forms and scripts."""
    BLOCK = {"p", "div", "br", "li", "tr", "section", "article", "main", "blockquote", "pre", "figcaption",
             "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt"}
    SKIP = {"script", "style", "noscript", "svg", "head", "template", "iframe", "button", "select"}
    SKIP_PAGE = {"nav", "header", "footer", "aside", "form", "menu", "dialog"}
    VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "area", "base", "col", "embed", "param", "track"}

    def __init__(self, page: bool = False, href: str = ""):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.href = href          # this file's path inside an EPUB, to resolve note links
        self.notes: dict = {}     # "file#id" -> text of a footnote or endnote found in this file
        self.noterefs: list = []  # "file#id" of each note this file's text points to, in order
        self.note_refs: dict = {} # "file#id" of a note -> the notes it points to itself
        self._note = None         # (key, stack depth) while inside a note
        self._drop = None         # stack depth while inside a backlink, whose text is dropped
        self.stack: list = []
        self.all, self.inside = [], []
        self.heading = None
        self.first_heading = None
        self.title = ""
        self.meta: dict = {}
        self.meta_all: dict = {}
        self._in_title = False

    def _skipping(self) -> bool:
        skip = self.SKIP | (self.SKIP_PAGE if self.page else set())
        return any(t in skip for t in self.stack)

    def _in_article(self) -> bool:
        return any(t in ("article", "main") for t in self.stack)

    def _emit(self, s: str) -> None:
        if self._note:
            self.notes[self._note[0]].append(s)
            return
        self.all.append(s)
        if self._in_article():
            self.inside.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"])
                self.meta_all.setdefault(key, []).append(a["content"])
            return
        if tag == "title":
            self._in_title = True
        if tag not in self.VOID:
            self.stack.append(tag)
        if self._skipping() or self._drop:
            return
        kinds = f"{a.get('epub:type') or ''} {a.get('role') or ''}".lower()
        if self.href and re.search(r"\b(doc-)?(endnote|footnote|rearnote)\b", kinds) and a.get("id") and not self._note:
            key = f"{self.href}#{a['id']}"
            self.notes[key] = []
            self._note = (key, len(self.stack))
            return
        if tag == "a" and re.search(r"\bbacklink\b", kinds):
            self._drop = len(self.stack)
            return
        if tag == "a" and re.search(r"\bnoteref\b", kinds) and a.get("href"):
            target, _, frag = a["href"].partition("#")
            path = posixpath.normpath(posixpath.join(posixpath.dirname(self.href), target)) if target else self.href
            if self._note:
                self.note_refs.setdefault(self._note[0], []).append(f"{path}#{frag}")
            else:
                self.noterefs.append(f"{path}#{frag}")
            self._emit(" [")
            self._closing_ref = len(self.stack)
            return
        if tag in self.BLOCK:
            self._emit("\n\n")
        if tag in ("h1", "h2", "h3"):
            self.heading = []
            self._emit("## ")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2", "h3") and self.heading is not None:
            name = " ".join("".join(self.heading).split())
            if name and self.first_heading is None:
                self.first_heading = name
            self.heading = None
        skipping = self._skipping() or bool(self._drop)
        depth = len(self.stack)
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        if self._drop and len(self.stack) < self._drop:
            self._drop = None
            return
        if getattr(self, "_closing_ref", None) and len(self.stack) < self._closing_ref:
            self._closing_ref = None
            self._emit("]")
            return
        if self._note and len(self.stack) < self._note[1]:
            self.notes[self._note[0]] = tidy("".join(self.notes[self._note[0]]))
            self._note = None
            return
        if not skipping and depth and tag in self.BLOCK:
            self._emit("\n\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skipping() or self._drop:
            return
        self._emit(data)
        if self.heading is not None:
            self.heading.append(data)

    def text(self) -> str:
        body = self.inside if self.page and words("".join(self.inside)) >= MIN_ARTICLE_WORDS else self.all
        return tidy("".join(body))


def page_to_text(data: bytes, url: str, ctype: str = "") -> dict:
    charset = None
    m = re.search(r'charset=["\']?([A-Za-z0-9_-]+)', ctype) or re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', data[:4000])
    if m:
        found = m.group(1)
        charset = (found.decode("ascii", "ignore") if isinstance(found, bytes) else found) or None
    try:
        text = data.decode(charset, "replace") if charset else data.decode("utf-8")
    except (LookupError, UnicodeDecodeError):  # no charset given and not UTF-8: old pages are usually Windows-1252
        text = data.decode("cp1252", "replace")
    p = TextOut(page=True)
    p.feed(text)
    body = p.text()
    meta = p.meta
    title = (meta.get("og:title") or p.first_heading or p.title or url).strip()
    author = (meta.get("author") or meta.get("article:author") or meta.get("parsely-author") or "").strip()
    if author.startswith("http"):
        author = ""
    date = (meta.get("article:published_time") or meta.get("date") or meta.get("parsely-pub-date") or "").strip()
    if words(body) < MIN_ARTICLE_WORDS:
        raise RuntimeError(
            "that page shows very little text. It may need a sign in, a subscription, or a browser to build it. "
            "Open it yourself, copy the article and paste it here, or use a web tool to get the full text")
    return {"title": html.unescape(title), "author": html.unescape(author), "date": date[:10], "text": body}


# ---------------------------------------------------------------- EPUB

def epub_chapters(path: Path):
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise RuntimeError("that EPUB is damaged or not really an EPUB") from None
    names = set(z.namelist())
    if "META-INF/rights.xml" in names:
        raise RuntimeError("that EPUB is locked with DRM. This skill reads only books that open freely and does "
                           "not unlock files")
    if "META-INF/encryption.xml" in names:
        enc = z.read("META-INF/encryption.xml").decode("utf-8", "replace")
        if any(not re.search(r"\.(otf|ttf|woff2?)$", u, re.I) for u in re.findall(r'URI="([^"]+)"', enc)):
            raise RuntimeError("that EPUB is locked with DRM. This skill reads only books that open freely and "
                               "does not unlock files")
    try:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = next(e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile"))
        opf = ET.fromstring(z.read(opf_path))
    except (KeyError, StopIteration, ET.ParseError):
        raise RuntimeError("that EPUB is missing its contents files, so it cannot be read in order") from None
    base = posixpath.dirname(opf_path)
    title = next((e.text for e in opf.iter() if e.tag.endswith("}title") and e.text), path.stem)
    author = next((e.text for e in opf.iter() if e.tag.endswith("}creator") and e.text), "")
    date = next((e.text for e in opf.iter() if e.tag.endswith("}date") and e.text), "")
    manifest = {e.get("id"): e for e in opf.iter() if e.tag.endswith("}item")}
    spine = [e.get("idref") for e in opf.iter() if e.tag.endswith("}itemref")]
    toc = {}
    for item in manifest.values():  # chapter names from the EPUB 3 nav or the EPUB 2 NCX
        href = posixpath.normpath(posixpath.join(base, item.get("href", "")))
        try:
            if "nav" in (item.get("properties") or ""):
                nav = z.read(href).decode("utf-8", "replace")
                for m in re.finditer(r'<a[^>]*href="([^"#]+)[^"]*"[^>]*>(.*?)</a>', nav, re.S):
                    toc.setdefault(posixpath.normpath(posixpath.join(posixpath.dirname(href), m.group(1))),
                                   " ".join(re.sub(r"<[^>]+>", "", html.unescape(m.group(2))).split()))
            elif item.get("media-type") == "application/x-dtbncx+xml":
                for pt in ET.fromstring(z.read(href)).iter():
                    if pt.tag.endswith("navPoint"):
                        label = next((t.text for t in pt.iter() if t.tag.endswith("text") and t.text), "")
                        src = next((c.get("src") for c in pt.iter() if c.tag.endswith("content")), "")
                        if src:
                            toc.setdefault(posixpath.normpath(posixpath.join(posixpath.dirname(href),
                                                                             src.split("#")[0])), label.strip())
        except (KeyError, ET.ParseError):
            continue
    docs, notes, note_refs = [], {}, {}
    for idref in spine:
        item = manifest.get(idref)
        if item is None:
            continue
        href = posixpath.normpath(posixpath.join(base, item.get("href", "")))
        try:
            p = TextOut(href=href)
            p.feed(z.read(href).decode("utf-8", "replace"))
        except KeyError:
            continue
        notes.update({k: (v if isinstance(v, str) else tidy("".join(v))) for k, v in p.notes.items()})
        note_refs.update(p.note_refs)
        text = p.text()
        if p.notes and words(text) < 100:  # a page that only holds endnotes: they go beside their chapters
            continue
        docs.append({"href": href, "text": text, "refs": p.noterefs, "heading": p.first_heading})
    chapters, carry, used = [], "", set()
    for d in docs:
        if words(d["text"]) < 60:  # covers, title pages and short dividers join the next chapter
            carry = (carry + "\n\n" + d["text"]).strip()
            continue
        name = toc.get(d["href"]) or d["heading"] or f"Part {len(chapters) + 1}"
        chapters.append({"title": name, "text": (carry + "\n\n" + d["text"]).strip(), "refs": d["refs"]})
        carry = ""
    if carry and chapters:
        chapters[-1]["text"] += "\n\n" + carry
    note_words = 0
    for ch in chapters:  # each chapter carries the notes it points to, numbered as in the book
        refs, lines = [], []
        for r in ch.pop("refs"):
            refs += [r] + note_refs.get(r, [])  # a note's own notes follow it
        for r in refs:
            if r not in notes or r in used:
                continue
            used.add(r)
            label = re.sub(r"^\D*", "", r.split("#")[-1]) or r.split("#")[-1]
            lines.append(f"[{label}] {notes[r]}")
            note_words += words(notes[r])
        if lines:
            ch["text"] += "\n\n## Notes To This Chapter\n\n" + "\n\n".join(lines)
    left = [k for k in notes if k not in used]
    if left and chapters:
        def tag(k):
            return re.sub(r"^\D*", "", k.split("#")[-1]) or k
        chapters.append({"title": "Other notes", "text": "\n\n".join(f"[{tag(k)}] {notes[k]}" for k in left)})
        note_words += sum(words(notes[k]) for k in left)
    # dc:date is usually this edition's date, not when the work was written, so it is kept apart.
    return {"title": title.strip(), "author": (author or "").strip(), "date": "", "edition_date": (date or "")[:10],
            "chapters": chapters, "note_words": note_words}


# ---------------------------------------------------------------- PDF

def ensure_pypdf():
    """pypdf is installed once into a private folder for this Python, then imported from there."""
    target = CACHE / "read-packages" / f"py{sys.version_info[0]}{sys.version_info[1]}"
    sys.path.insert(0, str(target))
    try:
        import pypdf  # noqa: F401
        quiet_pypdf()
        return pypdf
    except ImportError:
        pass
    log("Installing the PDF reader once (a few seconds).")
    target.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "--target", str(target), PYPDF], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("could not install the PDF reader (pypdf). " + (r.stderr.strip().splitlines() or [""])[-1]
                           + ". If pip is missing, install it (for example `python3 -m ensurepip`) and try again")
    import importlib
    importlib.invalidate_caches()
    import pypdf
    quiet_pypdf()
    return pypdf


def quiet_pypdf():
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings mean nothing to the person


def pdf_chapters(path: Path):
    pypdf = ensure_pypdf()
    try:
        r = pypdf.PdfReader(str(path))
    except Exception as exc:
        raise RuntimeError(f"that PDF would not open; it may be damaged ({type(exc).__name__})") from None
    if r.is_encrypted:
        try:
            ok = r.decrypt("")
        except Exception:
            ok = 0
        if not ok:
            raise RuntimeError("that PDF needs a password or is locked with DRM. This skill does not unlock files; "
                               "if it is yours to unlock, open it and save an unlocked copy")
    pages = []
    for pg in r.pages:
        try:
            pages.append(pg.extract_text() or "")
        except Exception:
            pages.append("")
    total = sum(words(p) for p in pages)
    if total < 20 * max(1, len(pages)) and total < 2000:
        raise RuntimeError("that PDF is pictures of pages with no text in it, like a scan. It needs text "
                           "recognition (OCR) first, for example in Preview, Acrobat or Google Drive")
    levels: dict = {}

    def walk(items, depth):
        for it in items:
            if isinstance(it, list):
                if depth < 1:
                    walk(it, depth + 1)
                continue
            try:
                levels.setdefault(depth, []).append((str(it.title).strip(), r.get_destination_page_number(it)))
            except Exception:
                pass
    try:
        walk(r.outline, 0)
    except Exception:
        pass
    meta = r.metadata or {}
    chapters = []
    # The top level of the table of contents is usually the chapters; when it is only parts, go one deeper.
    marks = levels.get(0, [])
    if len(marks) < 3 and len(levels.get(1, [])) >= 3:
        marks = levels[1]
    marks = sorted({(t, n) for t, n in marks if t and 0 <= n < len(pages)}, key=lambda m: m[1])
    if len(marks) >= 2:
        if marks[0][1] > 0:
            marks.insert(0, ("Front Matter", 0))
        for k, (t, start) in enumerate(marks):
            end = marks[k + 1][1] if k + 1 < len(marks) else len(pages)
            text = "\n\n".join(pages[start:end]).strip()
            if end > start and text:
                chapters.append({"title": t, "text": text, "pages": f"{start + 1} to {end}"})
    if not chapters:
        for start in range(0, len(pages), PAGES_PER_PART):
            end = min(len(pages), start + PAGES_PER_PART)
            text = "\n\n".join(pages[start:end]).strip()
            if text:
                chapters.append({"title": f"Pages {start + 1} to {end}", "text": text, "pages": f"{start + 1} to {end}"})
    merged = []
    for ch in chapters:  # very short sections join the one before
        if merged and words(ch["text"]) < 300:
            merged[-1]["text"] += "\n\n" + ch["text"]
            merged[-1]["pages"] = merged[-1]["pages"].split(" to ")[0] + " to " + ch["pages"].split(" to ")[1]
        else:
            merged.append(ch)
    chapters = merged
    title = str(meta.get("/Title") or "").strip()
    if not title or title.lower() in ("untitled", "microsoft word") or title.lower().endswith((".doc", ".docx", ".pdf")):
        title = path.stem
    return {"title": title, "author": str(meta.get("/Author") or "").strip(), "date": "",
            "chapters": chapters, "pages": len(pages)}


# ---------------------------------------------------------------- Word, text and HTML files

def docx_text(path: Path):
    try:
        z = zipfile.ZipFile(path)
        root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise RuntimeError("that Word file is damaged or not really a .docx") from None
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    out = []
    for para in root.iter(f"{w}p"):
        text = "".join(t.text or "" for t in para.iter(f"{w}t")).strip()
        if not text:
            continue
        style = para.find(f"{w}pPr/{w}pStyle")
        level = re.search(r"Heading([1-3])", style.get(f"{w}val", "")) if style is not None else None
        out.append(("## " if level else "") + text)
    title = path.stem
    try:
        core = ET.fromstring(z.read("docProps/core.xml"))
        title = next((e.text for e in core.iter() if e.tag.endswith("}title") and e.text), title)
        author = next((e.text for e in core.iter() if e.tag.endswith("}creator") and e.text), "")
    except (KeyError, ET.ParseError):
        author = ""
    return {"title": title, "author": author, "date": "", "text": "\n\n".join(out)}


def split_by_headings(text: str) -> list:
    """Chapters from '## ' headings, for a long text or Word file. One chapter if there are none."""
    parts = re.split(r"(?m)^## (.+)$", text)
    if len(parts) < 3:
        return [{"title": "Whole text", "text": text}]
    chapters = []
    if parts[0].strip():
        chapters.append({"title": "Opening", "text": parts[0].strip()})
    for k in range(1, len(parts), 2):
        chapters.append({"title": parts[k].strip(), "text": f"## {parts[k].strip()}\n\n{parts[k + 1].strip()}"})
    merged = []
    for ch in chapters:  # very short sections join the one before
        if merged and words(ch["text"]) < 300:
            merged[-1]["text"] += "\n\n" + ch["text"]
        else:
            merged.append(ch)
    return merged


# ---------------------------------------------------------------- one input to text

def paper_page(url: str) -> tuple[str, dict]:
    """An arXiv abstract page: the PDF link, and the title, authors and date from the page's own tags."""
    m = re.match(r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/([^?#]+?)(?:\.pdf)?$", url)
    if not m:
        return url, {}
    found = {}
    try:
        p = TextOut(page=True)
        p.feed(fetch_url(f"https://arxiv.org/abs/{m.group(1)}", limit=5 * 1024 ** 2).decode("utf-8", "replace"))
        found = {"title": p.meta.get("citation_title", ""), "author": ", ".join(p.meta_all.get("citation_author", [])[:6]),
                 "date": (p.meta.get("citation_date") or "").replace("/", "-")}
    except Exception:
        pass
    return f"https://arxiv.org/pdf/{m.group(1)}", {k: v for k, v in found.items() if v}


def from_file(path: Path, source: str) -> dict:
    ext = path.suffix.lower()
    if ext in LOCKED_EXT:
        raise RuntimeError(f"{path.name} is {LOCKED_EXT[ext]}, locked so only its own app can open it. This skill "
                           "does not unlock files. A DRM free EPUB or PDF of a book you own works")
    if ext in AUDIO_EXT:
        raise RuntimeError("that is an audio file. The listen skill handles audio and audiobooks")
    if ext == ".epub":
        got = epub_chapters(path)
        got["kind"] = "book"
    elif ext == ".pdf" or path.read_bytes()[:5] == b"%PDF-":
        got = pdf_chapters(path)
        got["kind"] = "book" if got["pages"] >= 80 else "document"
    elif ext == ".docx":
        got = docx_text(path)
        got["kind"] = "document"
    elif ext in TEXT_EXT:
        got = {"title": path.stem, "author": "", "date": "", "kind": "document",
               "text": path.read_text(encoding="utf-8", errors="replace")}
    elif ext in HTML_EXT:
        got = page_to_text(path.read_bytes(), source)
        got["kind"] = "article"
    else:
        raise RuntimeError(f"{path.name} is not a kind of file this skill reads. It reads EPUB, PDF, .docx, .txt, "
                           ".md and .html")
    return got


def from_link(url: str) -> dict:
    url, known = paper_page(url)
    typed_local = is_local(url)
    data, ctype = fetch_url(url, typed_local, limit=300 * 1024 ** 2, with_type=True)
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if ext in LOCKED_EXT or ext in AUDIO_EXT:
        raise RuntimeError("that link is " + ("a locked book file; this skill does not unlock files" if ext in
                           LOCKED_EXT else "audio; the listen skill handles audio"))
    if data[:5] == b"%PDF-" or "pdf" in ctype or data[:2] == b"PK":
        suffix = ".pdf" if data[:5] == b"%PDF-" else (".epub" if ext == ".epub" or "epub" in ctype else
                                                      ".docx" if ext == ".docx" else ".bin")
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / f"download{suffix}"
            f.write_bytes(data)
            got = from_file(f, url)
        if got["title"] == "download":
            name = urllib.parse.unquote(Path(urllib.parse.urlsplit(url).path).name)
            got["title"] = re.sub(r"\.(pdf|epub|docx)$", "", name, flags=re.I) or url
        got.update(known)
        if known and got["kind"] == "document":
            got["kind"] = "paper"
        return got
    if "text/plain" in ctype or ext in TEXT_EXT:
        return {"title": Path(urllib.parse.urlsplit(url).path).stem or url, "author": "", "date": "",
                "kind": "document", "text": data.decode("utf-8", "replace")}
    got = page_to_text(data, url, ctype)
    got["kind"] = "article"
    return got


def write_working(got: dict, source: str, page: str | None) -> dict:
    sid = make_id(got["title"], source)
    folder = working() / sid
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    chapters = got.get("chapters")
    if chapters is None:
        text = tidy(got["text"])
        chapters = split_by_headings(text) if words(text) > ONE_TEXT_LIMIT else [{"title": got["title"], "text": text}]
    total = sum(words(c["text"]) for c in chapters)
    one_text = total <= ONE_TEXT_LIMIT
    note = "Working copy for reading only. It is deleted when the notes are saved."
    meta = {"id": sid, "kind": got["kind"], "medium": "text", "made_by": "read", "title": got["title"],
            "author": got.get("author") or None, "date": got.get("date") or None, "source": source,
            "page": page, "how": "text taken from the file itself", "words": total}
    for k in ("pages", "note_words", "edition_date"):
        if got.get(k):
            meta[k] = got[k]
    if got.get("note_words"):
        meta["note_words_explained"] = ("the book's footnotes and endnotes, placed at the end of the chapter that "
                                        "points to them; often scholarly detail, so read them as needed")
    head = [f"# {got['title']}", "", f"Source: {source}"] + ([f"Author: {got['author']}"] if got.get("author") else [])
    if one_text:
        body = "\n\n".join((f"## {c['title']}\n\n{c['text']}" if len(chapters) > 1 else c["text"]) for c in chapters)
        (folder / "source.md").write_text("\n".join(head) + f"\n\n{note}\n\n{body}\n", encoding="utf-8")
        meta["layout"] = "one text"
    else:
        (folder / "chapters").mkdir()
        listing = []
        for n, ch in enumerate(chapters, 1):
            f = folder / "chapters" / f"{n:02d}.md"
            f.write_text(f"# {ch['title']}\n\n{note}\n\n{ch['text']}\n", encoding="utf-8")
            listing.append({"n": n, "title": ch["title"], "words": words(ch["text"]), "file": str(f),
                            **({"pages": ch["pages"]} if ch.get("pages") else {}),
                            **({"skip_suggested": True} if SKIP_TITLES.match(ch["title"].strip()) else {})})
        meta["layout"] = "chapters"
        meta["chapters"] = listing
    (folder / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    meta["folder"] = str(folder)
    if one_text:
        meta["source_file"] = str(folder / "source.md")
    return meta


def cmd_open(a) -> int:
    raw = a.source.strip()
    p = Path(raw).expanduser()
    try:
        if p.exists():
            if not p.is_file():
                log(f"FAILED: {p} is a folder. Give one file at a time.")
                return 1
            source, page = str(p.resolve()), None
            got = from_file(p, source)
        elif re.match(r"https?://", raw):
            got = from_link(raw)
            parts = urllib.parse.urlsplit(raw)
            if got["kind"] in ("book", "document") and Path(parts.path).suffix.lower() in (".epub", ".pdf", ".docx"):
                source, page = urllib.parse.urlunsplit(parts._replace(query="", fragment="")), None
            else:
                source = page = raw
        else:
            log(f"FAILED: not a link and not a file that exists: {raw}. Drag the file into the chat to give its path.")
            return 1
    except RuntimeError as exc:
        log(f"FAILED: {exc}.")
        return 2
    except OSError as exc:
        log(f"FAILED: could not read that ({exc}).")
        return 2
    if not got.get("chapters") and not got.get("text", "").strip():
        log("FAILED: found no readable text in that.")
        return 2
    meta = write_working(got, source, page)
    seen = source in learned_sources()
    log(f"OK {meta['title']}: {meta['words']:,} words, "
        + (f"{len(meta['chapters'])} chapters" if meta["layout"] == "chapters" else "one text")
        + (". Note: this is already in the library." if seen else "."))
    print(json.dumps(meta, indent=1, ensure_ascii=False))
    return 0


def cmd_status(a) -> int:
    target = CACHE / "read-packages" / f"py{sys.version_info[0]}{sys.version_info[1]}"
    try:
        sources = len(json.loads((library() / "library.json").read_text(encoding="utf-8")).get("items", {}))
    except (OSError, ValueError):
        sources = 0
    open_now = [p.name for p in working().iterdir() if p.is_dir() and (p / "meta.json").exists()] if working().exists() else []
    print(json.dumps({
        "python": ".".join(map(str, sys.version_info[:3])),
        "pdf_reader": "installed" if (target / "pypdf").exists() else "installed the first time a PDF is opened",
        "library": str(library()),
        "sources_in_library": sources,
        "open_in_working_folder": open_now,
    }, indent=1, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Get the text out of a book, paper, article or document.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open")
    p.add_argument("source")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    try:
        return {"open": cmd_open, "status": cmd_status}[a.cmd](a)
    except KeyboardInterrupt:
        log("Stopped.")
        return 130
    except Exception as exc:  # a plain sentence, never a stack trace
        log(f"FAILED: something unexpected went wrong ({type(exc).__name__}: {str(exc)[:300]}).")
        return 2


if __name__ == "__main__":
    sys.exit(main())
