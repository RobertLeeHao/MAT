# Shared parts

Pieces of the site that appear on more than one page are written once here and copied into each page by a script, so the pages stay single files with no build step and no runtime dependency.

## Top bar (`topbar.py`)
One top bar for every page: the main page's nav, the bar on top of the footer sheets (#changelog, #about …) and the Rankings page's nav. Same mark, height, hairline, link style and right-hand cluster; the links and the rightmost button change with the variant.

- Edit `parts/topbar.py` (markup in `page_bar()` / `sheet_bar()`, styles in `CSS`, which pages in `PAGES`), then run `python3 parts/topbar.py`.
- In the pages, the generated regions sit between `<!-- part:topbar -->` … `<!-- /part:topbar -->` (and `part:topbar:sheet`) and, in the stylesheet, `/* part:topbar */` … `/* /part:topbar */`. Don't edit inside them; the next run overwrites them.
- `publish.sh` runs it before committing. `python3 parts/topbar.py --check` exits 1 if a page is out of date.
- A new page: add the two marker regions to it and an entry in `PAGES`.
- Text inside the bar is English; the main page translates it through `i18n/` (the strings already have keys), the Rankings page sets its links and button from its own dictionary.
