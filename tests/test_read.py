"""Offline tests for read.py. Run: python3 -m unittest discover -s tests

PDF reading needs pypdf, which read.py installs on first use; it was checked live on real books and papers
rather than here, so these tests need no network.
"""
import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "read" / "scripts"
sys.path.insert(0, str(SCRIPTS))

PARA = ("Price from what the problem costs the buyer, not from your hours. Offer three options and put the "
        "middle one first, because most people pick it. ") * 6
ARTICLE = f"""<html><head><title>Site | Pricing</title><meta property="og:title" content="How To Price">
<meta name="author" content="Sam Writer"><meta property="article:published_time" content="2026-10-01T09:00:00Z">
<script>var x = "do not keep";</script></head><body>
<nav>Home About Subscribe Home About Subscribe</nav><header>Big site header text</header>
<article><h1>How To Price</h1><p>{PARA}</p><h2>Three options</h2><p>{PARA}</p></article>
<aside>Related posts you might like</aside><footer>Copyright footer</footer></body></html>"""


def make_epub(path: Path, locked: bool = False, chapters: int = 3):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""")
        if locked:
            z.writestr("META-INF/rights.xml", "<rights/>")
        items = "".join(f'<item id="c{n}" href="text/c{n}.xhtml" media-type="application/xhtml+xml"/>' for n in range(chapters))
        spine = "".join(f'<itemref idref="c{n}"/>' for n in range(chapters))
        z.writestr("OEBPS/content.opf", f"""<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"
xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>The Pricing Book</dc:title>
<dc:creator>Ada Author</dc:creator><dc:date>2024-05-01</dc:date></metadata>
<manifest><item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>
<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>{items}</manifest>
<spine><itemref idref="cover"/>{spine}</spine></package>""")
        links = "".join(f'<li><a href="text/c{n}.xhtml">Chapter {n + 1}: Part {n + 1}</a></li>' for n in range(chapters))
        z.writestr("OEBPS/nav.xhtml", f"<html><body><nav><ol>{links}</ol></nav></body></html>")
        z.writestr("OEBPS/text/cover.xhtml", "<html><body><p>The Pricing Book</p></body></html>")
        for n in range(chapters):
            z.writestr(f"OEBPS/text/c{n}.xhtml", f"<html><head><style>p{{}}</style></head><body><h1>Heading {n}</h1>"
                                                 f"<p>{PARA}</p><p>{PARA}</p></body></html>")


def make_docx(path: Path):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = (f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Pricing</w:t></w:r></w:p>'
            f'<w:p><w:r><w:t>{PARA}</w:t></w:r></w:p>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {w}><w:body>{body}</w:body></w:document>')
        z.writestr("docProps/core.xml", '<?xml version="1.0"?><cp:coreProperties xmlns:cp="x" '
                   'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Rate Card</dc:title>'
                   '<dc:creator>Pat</dc:creator></cp:coreProperties>')


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fn(*args)
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {"LEARNING_LIBRARY": str(self.root / "lib"), "LEARNING_SKILLS_CACHE": str(self.root / "cache")}
        self.old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        import library
        import read
        self.library = importlib.reload(library)
        self.read = importlib.reload(read)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def open(self, path):
        code, out = quiet(self.read.main, ["open", str(path)])
        meta = json.loads(out[out.index("{"):]) if "{" in out else None
        return code, out, meta


class Epub(Base):
    def test_short_book_is_one_text_with_chapter_names(self):
        f = self.root / "b.epub"
        make_epub(f)
        code, out, meta = self.open(f)
        self.assertEqual(code, 0, out)
        self.assertEqual(meta["title"], "The Pricing Book")
        self.assertEqual(meta["author"], "Ada Author")
        self.assertEqual(meta["kind"], "book")
        self.assertEqual(meta["layout"], "one text")
        text = Path(meta["source_file"]).read_text()
        self.assertIn("## Chapter 1: Part 1", text)
        self.assertIn("The Pricing Book", text)  # the short cover page joins the first chapter
        self.assertNotIn("p{}", text)

    def test_long_book_is_split_into_chapters(self):
        f = self.root / "b.epub"
        make_epub(f, chapters=3)
        self.read.ONE_TEXT_LIMIT = 100
        code, out, meta = self.open(f)
        self.assertEqual(meta["layout"], "chapters")
        self.assertEqual([c["title"] for c in meta["chapters"]], ["Chapter 1: Part 1", "Chapter 2: Part 2", "Chapter 3: Part 3"])
        self.assertTrue(Path(meta["chapters"][0]["file"]).exists())

    def test_drm_epub_is_refused(self):
        f = self.root / "locked.epub"
        make_epub(f, locked=True)
        code, out, _ = self.open(f)
        self.assertEqual(code, 2)
        self.assertIn("does not unlock", out)


def make_noted_epub(path: Path):
    """Two chapters pointing at endnotes kept in their own file, the way Standard Ebooks lays them out."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="e/content.opf"/></rootfiles></container>""")
        z.writestr("e/content.opf", """<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"
xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Noted</dc:title><dc:date>2020-10-21</dc:date></metadata>
<manifest><item id="a" href="t/one.xhtml"/><item id="b" href="t/two.xhtml"/><item id="i" href="t/imprint.xhtml"/>
<item id="n" href="t/endnotes.xhtml"/></manifest><spine><itemref idref="i"/><itemref idref="a"/><itemref idref="b"/>
<itemref idref="n"/></spine></package>""")
        z.writestr("e/t/imprint.xhtml", f"<html><body><h2>Imprint</h2><p>{PARA}</p></body></html>")
        for name, n in (("one", 1), ("two", 2)):
            z.writestr(f"e/t/{name}.xhtml", f'<html><body><h2>Chapter {n}</h2><p>{PARA}<a href="endnotes.xhtml#note-{n}" '
                                           f'epub:type="noteref">{n}</a> more words.</p><p>{PARA}</p></body></html>')
        z.writestr("e/t/endnotes.xhtml", """<html><body><section epub:type="endnotes"><h2>Endnotes</h2><ol>
<li id="note-1" epub:type="endnote"><p>First note text, see also<a href="endnotes.xhtml#note-3" epub:type="noteref">3</a>.
<a href="one.xhtml#noteref-1" epub:type="backlink">BACK</a></p></li>
<li id="note-2" epub:type="endnote"><p>Second note text. <a href="two.xhtml#noteref-2" epub:type="backlink">BACK</a></p></li>
<li id="note-3" epub:type="endnote"><p>A note on a note.</p></li>
</ol></section></body></html>""")


class Notes(Base):
    def test_endnotes_sit_beside_their_chapters(self):
        f = self.root / "n.epub"
        make_noted_epub(f)
        self.read.ONE_TEXT_LIMIT = 100
        code, out, meta = self.open(f)
        self.assertEqual(code, 0, out)
        titles = [c["title"] for c in meta["chapters"]]
        self.assertNotIn("Endnotes", " ".join(titles))
        one = Path(meta["chapters"][1]["file"]).read_text()
        self.assertIn("most people pick it. [1] more words", " ".join(one.split()))
        self.assertIn("[1] First note text", one)
        self.assertIn("[3] A note on a note.", one)  # a note's own note follows it
        self.assertNotIn("BACK", one)
        self.assertNotIn("Second note text", one)
        self.assertIn("[2] Second note text.", Path(meta["chapters"][2]["file"]).read_text())
        self.assertEqual(meta["edition_date"], "2020-10-21")
        self.assertIsNone(meta["date"])
        self.assertTrue(meta["chapters"][0].get("skip_suggested"))  # the imprint
        self.assertFalse(meta["chapters"][1].get("skip_suggested"))

    def test_chapter_notes_are_kept_in_full(self):
        f = self.root / "n.epub"
        make_noted_epub(f)
        self.read.ONE_TEXT_LIMIT = 100
        _, _, meta = self.open(f)
        folder = Path(meta["folder"])
        (folder / "chapters" / "02.notes.md").write_text("## The Method\n1. Chapter one's own lesson.\n")
        (folder / "notes.md").write_text("---\ntitle: Noted\nsource: x\nkind: book\ntopics: notes\n"
                                         "one_line: Notes go beside chapters.\n---\n\n## The Method\n1. Whole book.\n")
        code, out = quiet(self.library.main, ["save", meta["id"]])
        self.assertEqual(code, 0, out)
        saved = (self.library.library() / "notes" / f"{meta['id']}.md").read_text()
        self.assertIn("## Chapter Notes In Full", saved)
        self.assertIn("### 2. Chapter 1", saved)
        self.assertIn("Chapter one's own lesson.", saved)


class Refusals(Base):
    def test_kindle_and_audio(self):
        for name, says in (("b.azw3", "Kindle"), ("b.aax", "Audible"), ("b.mp3", "listen skill")):
            f = self.root / name
            f.write_bytes(b"x")
            code, out, _ = self.open(f)
            self.assertEqual(code, 2, name)
            self.assertIn(says, out)

    def test_unknown_file_type(self):
        f = self.root / "b.xyz"
        f.write_bytes(b"hello")
        code, out, _ = self.open(f)
        self.assertEqual(code, 2)
        self.assertIn("EPUB, PDF", out)

    def test_missing(self):
        code, out, _ = self.open(self.root / "nope.pdf")
        self.assertEqual(code, 1)


class Pages(Base):
    def test_article_keeps_only_the_article(self):
        got = self.read.page_to_text(ARTICLE.encode(), "https://e.com/p")
        self.assertEqual(got["title"], "How To Price")
        self.assertEqual(got["author"], "Sam Writer")
        self.assertEqual(got["date"], "2026-10-01")
        for gone in ("Subscribe", "Big site header", "Related posts", "Copyright", "do not keep"):
            self.assertNotIn(gone, got["text"])
        self.assertIn("## Three options", got["text"])

    def test_thin_page_says_what_to_do(self):
        with self.assertRaisesRegex(RuntimeError, "copy the article"):
            self.read.page_to_text(b"<html><body><p>Please sign in.</p></body></html>", "https://e.com")

    def test_saved_html_file(self):
        f = self.root / "post.html"
        f.write_text(ARTICLE)
        code, out, meta = self.open(f)
        self.assertEqual(meta["kind"], "article")

    def test_arxiv_links_go_to_the_pdf(self):
        self.read.fetch_url = lambda *a, **k: b"<html><meta name='citation_title' content='A Paper'></html>"
        url, known = self.read.paper_page("https://arxiv.org/abs/1706.03762v7")
        self.assertEqual(url, "https://arxiv.org/pdf/1706.03762v7")
        self.assertEqual(known["title"], "A Paper")
        self.assertEqual(self.read.paper_page("https://example.com/x")[0], "https://example.com/x")


class Documents(Base):
    def test_docx(self):
        f = self.root / "r.docx"
        make_docx(f)
        code, out, meta = self.open(f)
        self.assertEqual(code, 0, out)
        self.assertEqual(meta["title"], "Rate Card")
        self.assertIn("## Pricing", Path(meta["source_file"]).read_text())

    def test_long_text_splits_on_headings(self):
        f = self.root / "long.md"
        f.write_text("Intro words. " * 50 + "\n\n## One\n\n" + PARA * 3 + "\n\n## Two\n\n" + PARA * 3)
        self.read.ONE_TEXT_LIMIT = 100
        code, out, meta = self.open(f)
        self.assertEqual(meta["layout"], "chapters")
        self.assertEqual([c["title"] for c in meta["chapters"]], ["Opening", "One", "Two"])

    def test_read_then_save_round_trip(self):
        f = self.root / "r.docx"
        make_docx(f)
        _, _, meta = self.open(f)
        folder = Path(meta["folder"])
        (folder / "notes.md").write_text("---\ntitle: Rate Card\nsource: x\nkind: document\ntopics: pricing\n"
                                         "one_line: Charge for value.\n---\n\n## The Method\n1. Charge for value.\n")
        code, out = quiet(self.library.main, ["save", meta["id"]])
        self.assertEqual(code, 0, out)
        saved = (self.library.library() / "notes" / f"{meta['id']}.md").read_text()
        self.assertIn("author: Pat", saved)
        self.assertIn(str(f.resolve()), saved)
        self.assertFalse(folder.exists())


class Where(Base):
    def test_lists_installed_skills(self):
        skill = self.root / "claude" / "skills" / "deals"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: deals\ndescription: Prepare for a negotiation.\n---\n")
        folded = self.root / "claude" / "skills" / "plans"
        folded.mkdir(parents=True)
        (folded / "SKILL.md").write_text("---\nname: plans\ndescription: >-\n  Write a plan\n  for the week.\nother: x\n---\n")
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.root / "claude")
        try:
            code, out = quiet(self.library.main, ["where"])
        finally:
            os.environ.pop("CLAUDE_CONFIG_DIR")
        self.assertEqual(json.loads(out)["skills_installed_claude_code"],
                         {"deals": "Prepare for a negotiation.", "plans": "Write a plan for the week."})


class SharedLibrary(unittest.TestCase):
    def test_library_py_matches_the_other_skills(self):
        """listen, read and watch carry the same library.py; a change to one goes to all."""
        checked = 0
        mine = (SCRIPTS / "library.py").read_text()
        for other in ("listen", "watch"):
            theirs = SCRIPTS.parent.parent / other / "scripts" / "library.py"
            if theirs.exists():
                checked += 1
                self.assertEqual(mine, theirs.read_text(), f"{other}/scripts/library.py differs; copy it across")

        if not checked:
            self.skipTest("the sibling skills are not in this repository")

if __name__ == "__main__":
    unittest.main()
