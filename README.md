# Read

**Claude can now read.** Give it a whole book you own, a paper, a report or a web article. It
reads all of it, learns what it teaches, keeps the notes in a library on your computer, and
turns them into a new skill you can use from then on.

Free. No API keys. Nothing to sign up for. Works in **Claude Code** and **Codex**.

**One of three.** Claude can also listen to podcasts with [listen-skill](https://github.com/psabbagh/listen-skill) and watch
videos with [watch-skill](https://github.com/psabbagh/watch-skill). Install any of them: they all keep their notes in the same library.

## 1. Install it

**Claude Code.** Open your computer's terminal and run these two commands, one at a time:

```bash
claude plugin marketplace add psabbagh/read-skill
```

```bash
claude plugin install read@read-skill
```

You can also type the same two lines inside Claude Code, starting with `/plugin` instead of
`claude plugin`.

**Codex.** In your terminal:

```bash
codex plugin marketplace add psabbagh/read-skill
```

```bash
codex plugin add read@read-skill
```

Then start a new Claude Code or Codex session so it picks up the skill.

## 2. Paste this first

Copy this into the chat, with your own book or link and your own goal:

```text
Read this: [file or link]. Learn what it teaches and turn it into a skill I can use forever, for [what you want it for].
```

For example: *Read this: ~/Downloads/the-book.epub. Learn what it teaches and turn it into a
skill I can use forever, for pricing my services.*

In the Claude desktop app you can drag the file into the chat instead of typing its path.

You do not have to type a command; asking is enough. If you prefer a command, type `/read`
in Claude Code and pick **read:read**, or type `$` in Codex and pick **read**.

## What it can read

| Give it | What it does |
|---|---|
| **An EPUB book without DRM** (from Standard Ebooks, Project Gutenberg, or an author or store that sells DRM-free) | The whole book, split into chapters from its own table of contents |
| **A PDF with real text in it**: a book, a report, a white paper, a research paper | The whole thing; a long one is split into chapters |
| **A link to a web article**: a blog post, a newsletter issue, a news story | The article's text |
| **A link to a PDF or EPUB file** | Downloads it and reads it as above |
| **An arXiv paper link** (the abstract page or the PDF) | The paper, with its title, authors and date |
| **A Word document (.docx)** | The document |
| **A text, Markdown or saved web page file** (.txt, .md, .html) | The file |

Footnotes and endnotes are kept with the chapter that points to them. For a book over about
50,000 words it tells you the size first and offers to read only the chapters that matter
for your goal.

**What it cannot read:**

- **Kindle books** (.azw, .azw3, .kfx, .mobi), **Audible**, **library loans** and other
  **DRM-locked** EPUBs or PDFs. Refused, never unlocked.
- **Scanned PDFs** (pictures of pages, no text). Run text recognition first: Preview on a Mac,
  Acrobat, or Google Drive can do it.
- **Old Word files** (.doc). Save as .docx first.
- **Articles behind a sign-in or paywall**, or pages that only load with JavaScript. Open the
  article yourself, copy the text and paste it into the chat; it carries on from there.
- **Audiobooks and podcasts.** Those go to
  [listen-skill](https://github.com/psabbagh/listen-skill).

## What happens

1. It opens the file and tells you how long it is. A long book is split into chapters using
   the book's own table of contents, and helper agents read the chapters. For a very long
   book it offers to read only the chapters that matter for your goal.
2. It writes notes in its own words: the method, the rules, the examples, the mistakes to
   avoid.
3. It drafts a new skill from those notes, tries it on a made-up example, and **shows you the
   whole skill before saving anything**. Nothing is saved until you say yes.
4. From then on you run your new skill by its name, like any other.

Ask it later *"what does my library say about hiring?"* and it answers from your notes,
naming each source.

## What it needs

- **Claude Code** (a paid Claude plan) or **Codex** (a ChatGPT plan that includes it).
- **Python 3.9 or newer.** The Python that comes with macOS works. If yours is missing, the skill tells you and asks before
  installing one.
- **It installs its own tools.** The first time it opens a PDF it fetches a PDF reader into a
  private folder (`~/.cache/learning-skills`) and says so.
- No API keys and no accounts.

## What it does not do

- **No unlocking.** For a locked book it tells you what you can do instead, such as buying a
  DRM-free edition, or dictating your own notes for it to file.
- **No book text kept.** The library keeps notes in its own words and the skills made from
  them, never the book's text. The text sits in a working folder while it reads and is deleted
  once the notes are saved.
- **It does not obey what it reads.** Anything written in a book or page is treated as
  material to learn from, never as instructions. A skill it writes never runs commands or
  sends data unless you approve each one by name.

## Where your library lives

In `~/learning-library` (a folder called `learning-library` in your home folder). Each source
gets its own notes, and `INDEX.md` lists them all. To keep it somewhere else, set the
`LEARNING_LIBRARY` environment variable to another folder.

The same library is shared by all three skills, so notes from a podcast, a book and a video
end up in one place.

## The other two

- **[listen-skill](https://github.com/psabbagh/listen-skill)**: Claude can now listen. A
  podcast, a whole show, a YouTube video or an audio file.
- **[watch-skill](https://github.com/psabbagh/watch-skill)**: Claude can now watch. A video
  where the slides, screens or demo matter.

## Uninstall

```bash
claude plugin uninstall read@read-skill
```

```bash
codex plugin remove read@read-skill
```

Your library in `~/learning-library` and the skills you made stay where they are.

## For developers

The skill is in [`skills/read/`](skills/read/). Tests run with the standard library:

```bash
python3 -m unittest discover -s tests
```

## License

MIT. See [LICENSE](LICENSE).
