#!/usr/bin/env python3
"""The site's top bar, as one component (2026-10-19).

Every page's top bar is written from here: the main page's nav, the bar on
top of the footer sheets (#changelog, #about …) and the Rankings page's nav.
Same mark, same height, same hairline, same right-hand cluster; only the
links and what the rightmost button does change.

    python3 parts/topbar.py          # rewrite the bar in every page
    python3 parts/topbar.py --check  # exit 1 if a page is out of date

Each page holds two generated regions — edit here, never there:
    <!-- part:topbar[:variant] -->  …markup…  <!-- /part:topbar[:variant] -->
    /* part:topbar */  …css…  /* /part:topbar */
publish.sh runs this before it commits, so a page can't ship a stale bar.
"""
import re, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The mark: the three figures at rest, as the main page's nav has always
# drawn them (white in front, copper and violet behind and smaller). One
# drawing for every bar, so the logo can't differ from page to page.
MARK = ('<svg class="mark" viewBox="0 0 22 22" aria-hidden="true">'
        '<circle cx="16" cy="11" r="3.5" fill="#9882CF"/>'
        '<circle cx="11.9" cy="11" r="4.15" fill="#C98565"/>'
        '<circle cx="7.2" cy="11" r="5" fill="#F4EFE6"/></svg>')

SECTIONS = [("#answer", "Why MAT"), ("#race", "What it saves"), ("#work", "How it works"),
            ("#ranks", "Models"), ("rankings/", "Rankings"), ("#private", "Privacy"), ("#faq", "Questions")]
SHEETS = [("#install", "Get the beta"), ("#changelog", "Changelog"), ("#about", "About"),
          ("#privacy", "Privacy"), ("#terms", "Terms"), ("#contact", "Contact")]

GITHUB = ('<a class="lang-b gh-b" href="https://github.com/RobertLeeHao/MAT" target="_blank" rel="noopener">'
          '<span>GitHub</span><svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 8 8 2M3.5 2H8v4.5"/></svg></a>')
LANG = ('<button class="lang-b" type="button" data-lang-menu aria-haspopup="menu" aria-expanded="false" '
        'aria-label="Language" data-i18n-skip><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5"/>'
        '<path d="M1.5 8h13M8 1.5c-2 2.2-2 10.8 0 13M8 1.5c2 2.2 2 10.8 0 13"/></svg><span class="lang-c"></span></button>')


def page_bar(prefix, current=None):
    """The nav at the top of a page. prefix: the way back to the main page
    from this one ('' on the main page, '../' one folder down)."""
    def href(h):
        if h == "rankings/":
            return "./" if prefix else "rankings/"
        return (prefix or "") + h
    links = "".join(
        '<a href="%s"%s>%s</a>' % (href(h), ' class="cur" aria-current="page"' if h == current else "", t)
        for h, t in SECTIONS)
    home = prefix if prefix else "#hero"
    return ('<header class="nav g" id="nav">\n'
            '  <a class="logo" href="%s" aria-label="MAT home">%sMAT</a>\n'
            '  <nav class="links" aria-label="Sections" id="navLinks">%s</nav>\n'
            '  <div class="cta">%s%s<a class="btn primary md" href="%s#join" id="navJoin"><span class="bl">Get the beta</span></a></div>\n'
            '</header>') % (home, MARK, links, GITHUB, LANG, prefix)


def sheet_bar():
    """The bar on top of the footer sheets: same bar, the sheet pages as its
    links, and Close where the call to action sits."""
    links = "".join('<a href="%s" data-sheet>%s</a>' % (h, t) for h, t in SHEETS)
    return ('<div class="sh-bar g"><a class="logo" href="#" data-close aria-label="Close and go back to the page">%sMAT</a>'
            '<nav class="sh-nav" aria-label="Pages">%s</nav>'
            '<div class="cta">%s<button class="sh-x" type="button" data-close aria-label="Close">Close<i aria-hidden="true"></i></button></div></div>'
            ) % (MARK, links, LANG)


CSS = r"""
/* ── top bar (one component for every page: parts/topbar.py) ── */
.nav{position:fixed;inset:0 0 auto 0;z-index:40;height:var(--navh);align-items:center;background:var(--ground)}
.nav:after,.sh-bar:after{content:"";position:absolute;left:var(--m);right:var(--m);bottom:0;border-top:var(--hair)}
.sh-bar{flex:none;height:var(--navh);align-items:center;position:relative}
.logo{grid-column:1/4;display:flex;align-items:center;gap:var(--s3);font-family:var(--display);font-weight:700;font-size:calc(15*var(--px));letter-spacing:-.01em}
.logo .mark{flex:none;width:calc(22*var(--px));height:calc(22*var(--px))}
html[data-ground="paper"] .nav .logo .mark{filter:invert(1) hue-rotate(180deg)}
.links,.sh-nav{display:flex;gap:var(--s5);font-size:calc(13*var(--px));line-height:calc(16*var(--px));font-weight:500;color:var(--mute)}
.links{grid-column:4/9} .sh-nav{grid-column:4/11}
.links a,.sh-nav a{text-box:trim-both cap alphabetic;white-space:nowrap}
html:is(:lang(es),:lang(fr),:lang(de)) :is(.links,.sh-nav){gap:var(--s4)}
.links a:hover,.links a.cur,.sh-nav a:hover,.sh-nav a[aria-current="page"]{color:var(--paper)}
.nav .cta,.sh-bar .cta{grid-column:11/13;display:flex;justify-content:flex-end;align-items:center;gap:calc(8*var(--px))}
.nav .cta .btn{transition:opacity .25s var(--out3)}
.sh-x{display:flex;align-items:center;gap:var(--s3);height:calc(36*var(--px));padding:0 var(--s3);border:0;background:none;color:var(--mute);font-size:calc(13*var(--px));font-weight:600;cursor:pointer;box-shadow:inset 0 0 0 .5px var(--hc2)}
.sh-x:hover{color:var(--paper)}
.sh-x i{position:relative;width:calc(10*var(--px));height:calc(10*var(--px));background:linear-gradient(currentColor,currentColor) center/100% 1.25px no-repeat,linear-gradient(currentColor,currentColor) center/1.25px 100% no-repeat;transform:rotate(45deg)}
.sh-x:focus-visible,.sh-nav a:focus-visible,.links a:focus-visible{outline:1px solid var(--amber);outline-offset:2px}
.lang-b{flex:none;display:inline-flex;align-items:center;gap:calc(6*var(--px));height:calc(36*var(--px));padding:0 calc(10*var(--px));border:0;background:none;color:var(--mute);font:600 calc(12*var(--px))/1 var(--text);cursor:pointer;box-shadow:inset 0 0 0 .5px var(--hc2);transition:color .15s}
.lang-b:hover,.lang-b[aria-expanded="true"]{color:var(--paper)}
.lang-b svg{flex:none;width:calc(14*var(--px));height:calc(14*var(--px));fill:none;stroke:currentColor;stroke-width:1.1}
.lang-b:focus-visible{outline:1px solid var(--amber);outline-offset:2px}
.lang-b span{text-box:trim-both cap alphabetic}
.lang-b.wide{height:auto;padding:0;box-shadow:none;font:inherit;color:var(--dim)}
.lang-b.wide:hover{color:var(--paper)}
.gh-b{text-decoration:none}
.gh-b svg{width:calc(9*var(--px));height:calc(9*var(--px))}
/* the section links leave the row when it gets tight; GitHub goes to the footer on phones and while the links share the row */
@media (max-width:1080px){ .links,.sh-nav{display:none} .nav .cta,.sh-bar .cta{grid-column:7/13} }
@media (max-width:1240px){ html:lang(fr) .links{display:none} html:lang(fr) .nav .cta{grid-column:7/13} }
@media (max-width:699px), (min-width:1081px) and (max-width:1279px){ .nav .gh-b{display:none} }
@media (max-width:860px), (max-width:1199px) and (orientation:portrait){ .logo{grid-column:1/7} .nav .cta,.sh-bar .cta{grid-column:7/-1} }
"""

PAGES = {
    "index.html": {"page": page_bar("", None), "sheet": sheet_bar()},
    "rankings/index.html": {"page": page_bar("../", "rankings/")},
}


def render(path, parts):
    s = open(os.path.join(ROOT, path), encoding="utf-8").read()
    out = s
    for variant, html in parts.items():
        tag = "topbar" if variant == "page" else "topbar:" + variant
        pat = re.compile(r"(<!-- part:%s -->\n?).*?(\n?\s*<!-- /part:%s -->)" % (re.escape(tag), re.escape(tag)), re.S)
        if not pat.search(out):
            sys.exit("%s: no <!-- part:%s --> region" % (path, tag))
        out = pat.sub(lambda m: m.group(1) + html + m.group(2), out, count=1)
    pat = re.compile(r"(/\* part:topbar \*/).*?(/\* /part:topbar \*/)", re.S)
    if not pat.search(out):
        sys.exit("%s: no /* part:topbar */ css region" % path)
    out = pat.sub(lambda m: m.group(1) + CSS + m.group(2), out, count=1)
    return s, out


if __name__ == "__main__":
    check = "--check" in sys.argv
    stale = []
    for path, parts in PAGES.items():
        before, after = render(path, parts)
        if before != after:
            stale.append(path)
            if not check:
                open(os.path.join(ROOT, path), "w", encoding="utf-8").write(after)
    if check:
        print("stale: " + ", ".join(stale) if stale else "top bar up to date")
        sys.exit(1 if stale else 0)
    print("rewrote: " + ", ".join(stale) if stale else "top bar already up to date")
