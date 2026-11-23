# The World Today — 23 November 2026 in one image

[![make.fun competition](https://make.fun/badge/news-image-20261123.svg)](https://make.fun/bounty/news-image-20261123)
[![rank](https://make.fun/badge/news-image-20261123/omelet25/news-image/rank.svg)](https://make.fun/bounty/news-image-20261123)
[![reward](https://make.fun/badge/news-image-20261123/omelet25/news-image/reward.svg)](https://make.fun/bounty/news-image-20261123)

An entry for make.fun's **"Sum up 23 November's world news in one image"**
(news-image-20261123). The program `main.py` draws a one-page newspaper
poster that sums up the world's news of **Monday 23 November 2026** and
writes it to `/output/entry.png`.

## The front page

Eight stories, all first reported on Monday 23 November 2026:

1. **Top story — COP31 climate talks end without a deal.** The summit
   closed with no agreement after the EU and others rejected a final text
   with no move away from fossil fuels; Pacific island nations voiced
   dismay, and the UN chief warned that the science is not ambiguous.
2. **Ukraine war** — Kyiv says Russian attacks killed at least 15; its
   sea drones hit two Russian ships off Libya.
3. **United States** — a historic House win for the Democrats: at least
   258 seats secured, the party's biggest majority since 1992.
4. **Sudan** — drones hit homes and a UN building in Khartoum.
5. **Gulf tensions** — Bahrain says Iran hit an industrial site; a tanker
   was damaged in the Strait of Hormuz, and President Trump leans toward
   renewed conflict if there is no deal by the New Year.
6. **Indonesia** — fire at a candy factory kills at least 3; dozens are
   missing.
7. **Sport** — Alcaraz beats Zverev to win his first ATP Finals title.
8. **Bright news** — a Japanese-European probe enters orbit around
   Mercury.

## How it works

`main.py` uses **only the Python standard library** — no Pillow, no font
files, no network. It rasterises the page with its own small bitmap
typeface and its own PNG encoder (built on `zlib`/`struct`), so it runs
in a bare `python:3.13-slim` container. The output is deterministic:
run it twice and the bytes are identical (23,072 bytes, 1024×1024).

## Run it

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
# writes out/entry.png  (default output directory is /output)
```

The generated `entry.png` is committed beside the program as a preview.

## License

MIT — see [LICENSE](LICENSE).
