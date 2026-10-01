# Slides

Slides are written in Markdown and turned into PDFs with [Marp](https://marp.app/).

```
decks/        one Markdown file per deck (lektion01.md, …), images in decks/img/
theme/        kurs.css (the slide theme) and the Fira Sans font files
pdf/          build output (ignored by git)
```

## Build

Needs Node.js 18+ and Chrome, Chromium, Edge or Firefox.

```sh
cd course/slides
npm install        # once
npm run build      # all decks in decks/ -> pdf/
npm run watch      # rebuild on every save
```

If no browser is found, point Marp to one, e.g. `CHROME_PATH=/path/to/chrome npm run build`.

Live preview while writing: install the VS Code extension *Marp for VS Code*
(`marp-team.marp-vscode`). The repo settings already register the theme.

## Writing a deck

Start every deck with:

```markdown
---
marp: true
---
```

Slides are separated by `---`. See `decks/beispiel.md` for every slide type.

| Slide type | How |
|---|---|
| Content slide | `# Heading`, then text, lists, formulas, code |
| Title slide | `<!-- _class: title -->` at the top of the slide |
| Chapter slide | `<!-- _class: chapter -->` at the top of the slide |
| Text left, image right | `![bg right:45% contain](img/file.png)` anywhere in the slide |
| Full-slide image | `![bg contain](img/file.png)` |

- Formulas: `$…$` inline, `$$…$$` as a block.
- Page numbers: add `paginate: true` to the deck's front matter.
- Footer text: add `footer: "…"` to the front matter.

## Changing the look

Everything is in `theme/kurs.css`. Colours and fonts are variables at the top
(`--text`, `--muted`, `--font`, …). The theme expects decks to sit directly in
`decks/`, because the font paths are relative to the deck.
