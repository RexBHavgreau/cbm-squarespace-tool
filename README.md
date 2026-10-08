# CBM Article Converter

Turns a finished article into HTML ready to paste into a Squarespace
Code Block, with working footnotes, pull quotes and Scripture
formatting. Developed for the Center for Biblical Missions'
publishing workflow.

It reads two kinds of article:

- a Word document (`.docx`)
- an InDesign export (`.html`)

## Getting it

Download the newest release from the
[Releases page](../../releases). The Windows `.exe` and the macOS
`.app` each contain everything they need; nothing has to be
installed.

Neither is code-signed, so the first run on a machine is challenged.
On Windows choose **More info**, then **Run anyway**. On macOS
right-click the app and choose **Open**, then confirm.

## Documentation

For whoever builds the web pages, there is a guide with live examples:
**[Building a CBM article page](https://rexbhavgreau.github.io/cbm-squarespace-tool/)**.
Bookmark it; it always matches the current release.

The app carries its own copies of these, reachable from the Guide button:

- `USER-GUIDE.txt` - for editors
- `HTML-REFERENCE.txt` - what the generated HTML looks like
- `BUILD-NOTES.txt` - building the app from source

## Versioning

This follows semantic versioning, with the levels defined against
the two things people actually depend on: the HTML the tool emits,
and the Word styles the template must provide.

| Change | Meaning |
| --- | --- |
| MAJOR | The HTML changed in a way whoever maintains the site must respond to, or the Word template needs new or renamed styles. Read the notes before updating. |
| MINOR | Something new. Nothing to do. |
| PATCH | A fix. Nothing to do. |

Version 1.0.0 was the first release. The work before it was numbered
Build 1 to Build 49 during development; articles converted in that
period carry a stamp reading `Build nn` rather than a version
number.

## Releases

### 1.5.0

Photographs. A picture in a Word document is no longer written into the
article as a megabyte of encoded text. Each one is saved to a folder
beside the article, and the article carries a conspicuous marker where
it belongs. How wide the picture is shown in Word becomes its share of
the text column, so it keeps its own shape; Word's text wrapping becomes
a float, with the picture taking the full column on a narrow screen. Alt
text and a Word caption come across, and any picture without alt text is
reported. Designer then Place the pictures swaps the markers for the real
thing once they have been uploaded, with a srcset so the browser takes a
suitable size.

Footnote callouts are fixed. Every Word-track article until now had its
reference numbers in square brackets, which came from the Word reader's
own default; they are now bare numerals, matching the InDesign track. A
reference that an author also superscripted by hand arrived wrapped
twice and rendered microscopically; those are now unwrapped.

**Articles published before this release should be reconverted and
re-pasted** — for the brackets, and because they still carry their own
copy of the styling from before 1.4.0 moved it to Custom CSS. The
stylesheet has new rules for figures, so re-export it from Designer.

### 1.4.0

A linked byline. The Author style now produces "By" and the names in
the order written, each linked to that author's profile page, with the
address worked out from the name. Articles with no profile page yet are
flagged above the code with the exact address to create.

A Designer menu: every article style laid out by element with a browser
preview, the stylesheet ready to paste into Custom CSS, and a builder
for article link cards on profile pages.

Styling has moved off the article. The .txt carries classes only, so
the look comes from Custom CSS and one edit reaches every article ever
published. The .html still carries the styling so it renders on its own
when checked. **Articles published before this release keep their own
copy of the old styling and should be reconverted and re-pasted.**

Also: styles are applied to whichever Word documents are already
chosen, several at once; a pull quote can no longer be the last thing
in an article; blurbs and article notes are centred; Hebrew inside an
English sentence is tagged; and the update download now opens at the
folder the app is in.

### 1.3.0

Preferences. What goes into an article, and in what order, is now yours
to set: the blurb, article note, reading time, author bio and a new
article-wide share row can each be included or left out and moved
around the article body. Heading alignment, reading speed, whether the
article carries its own styling, and where finished files are written
are all settings too, with one button to put everything back to the
defaults. The guides open inside the app, and an article can be dropped
straight onto the application.

### 1.2.0

The guides come with the app: a Guide button opens them, so they always
match the version in use. A release that carries no download for your
machine now says so rather than offering the wrong one. Adds a page for
whoever builds the web pages, published at the address above.

### 1.1.0

Checks GitHub for a newer version, at startup and on demand, and
offers to download it to a folder of your choosing. The new version
is saved alongside the old one rather than replacing it. The startup
check can be switched off in the window.

### 1.0.0

First release. Converts Word documents and InDesign exports into
HTML for a Squarespace Code Block: footnotes that link both ways,
pull quotes placed beside the paragraphs they quote, verse, Hebrew
set right to left, reading time, and the house front matter.

Every converted file begins with a hidden comment naming the version
that made it, so a published article can always be traced back.

## Licence

MIT. See `LICENSE`.
