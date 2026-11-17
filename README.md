# Read

**Claude can now read.** Give it a whole book you own, a paper, a report or a web article. It
reads all of it, learns what it teaches, keeps the notes in a library on your computer, and
turns them into a new skill you can use from then on.

Free. No API keys. Nothing to sign up for. Works in **Claude Code** and **Codex**.

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

It takes an EPUB or PDF without DRM, a Word, text or Markdown file, a saved web page, a link
to an article, or a link to a PDF or arXiv paper. In the Claude desktop app you can drag the
file into the chat instead of typing its path.

You do not have to type a command; asking is enough. If you prefer a command, type `/read`
in Claude Code and pick **read:read**, or type `$` in Codex and pick **read**.

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

- **No locked books.** Kindle and Audible files, library loans and other DRM-protected EPUBs
  and PDFs are refused, never unlocked. It tells you what you can do instead, such as buying a
  DRM-free edition, or dictating your own notes for it to file.
- **No scanned pages.** A scan has pictures of pages and no text. Run text recognition first
  (Preview on a Mac, Acrobat or Google Drive can do it).
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
