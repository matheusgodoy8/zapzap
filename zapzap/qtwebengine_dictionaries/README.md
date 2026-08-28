# Brazilian Portuguese spell-check dictionary

Official builds fetch `pt_BR.bdic` from Chromium's versioned
`hunspell_dictionaries` repository at revision
`cccf64a8acc951afe3f47fee023908e55699bc58` and verify SHA-256
`6b2850f5a54994a5204a9a88d4b586e9d4e028a0360b67352b04cffdb2a3e0ea`.

The upstream file is named `pt-BR-3-0.bdic`. ZapZap installs it as
`pt_BR.bdic` so that the existing stable locale identifier remains compatible
with persisted settings. Chromium documents this binary as generated from the
corresponding Hunspell `pt_BR.aff`, `pt_BR.dic`, and `pt_BR.dic_delta` files.

Source and notices:

- https://chromium.googlesource.com/chromium/deps/hunspell_dictionaries/+/cccf64a8acc951afe3f47fee023908e55699bc58/
- https://chromium.googlesource.com/chromium/deps/hunspell_dictionaries/+/cccf64a8acc951afe3f47fee023908e55699bc58/README_pt_BR.txt
- https://chromium.googlesource.com/chromium/deps/hunspell_dictionaries/+/cccf64a8acc951afe3f47fee023908e55699bc58/LICENSE

The upstream catalog describes the dictionaries as available under its
GPL/LGPL/MPL license set. ZapZap itself is distributed under GPL-3.0-or-later.
