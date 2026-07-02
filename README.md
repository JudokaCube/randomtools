<div align="center">

# ascii

**turn any image into ASCII art, right in your terminal**

![Python](https://img.shields.io/badge/Python-000000?style=for-the-badge&logo=python&logoColor=00ffff)
![Pillow](https://img.shields.io/badge/Pillow-000000?style=for-the-badge&logo=python&logoColor=00ffff)

</div>
<br>

Works with any image format — PNG, JPG, WEBP, BMP, GIF, TIFF, and more. Transparent backgrounds are respected, so the output follows your subject's silhouette instead of a rectangle. Full 24-bit color, multiple charsets, clipboard copy, animated GIF playback, batch processing, export to `.txt` / `.png` / `.html`.

```
                           =++++=
                     ++++++++++++++++++
                  ++++++++++++++++++++++++
                +++++++++++++++++++++++++++++
             +++++++++++++++====+++++++++++++++=
          =+++++++++++++++===--===+++++++++++++++=
          =+++++++++++++=-::::::::--=+++++++++++++=
        =++++++++++++-:::::::::::::::::=++++++++++++
        ++++++++++++=-:::::::::::::::::=++++++++++++
          +++++++++++++=-::::::::::-=+++++++++++++=
           =++=++++++++++++++++++++++++++++++=++=
              ++++++++++++++++++++++++++++++++=
                     +++++++++++++++++++
                          ++++++=++
```
<sub>renders in full color in an actual terminal</sub>
<br><br>

## Install

Works the same way on **Linux, macOS, and Windows** — it's a single Python script, no build step, no executable to compile.

```bash
pip install Pillow
```

That's it. Keep `ascii.py` wherever you like and run it with `python` (or `python3`, depending on your setup):

```bash
python ascii.py dragon.png
```

**Clipboard (`--copy`):** works out of the box everywhere — `pbcopy` on macOS, `clip` on Windows, and `wl-copy`/`xclip`/`xsel` on Linux (or `pip install pyperclip` as a universal fallback on any OS).

**File picker (no arguments):** on Linux, install whichever you already have — `zenity`, `yad`, `wofi`, or `rofi`. On macOS it uses the native picker automatically. Everywhere else (including Windows, or Linux without those tools) it falls back to Python's built-in Tk file dialog — no extra install needed on the standard Windows/macOS Python installers; on some Linux distros you may need `sudo apt install python3-tk`.

Want to type just `ascii` instead of `python ascii.py`? Make an alias/shell function (Linux/macOS: `alias ascii="python3 /path/to/ascii.py"` in your `.bashrc`/`.zshrc`) or a one-line `ascii.bat` on Windows (`@echo off` / `python "%~dp0ascii.py" %*`) and put it on your `PATH` — but that's entirely optional.

## Usage

**No idea what to type? Just run it:**

```bash
python ascii.py
```

This opens a file picker (or falls back to typing a path), then walks you through size, charset, color, and export options with a simple numbered menu — no flags required.

**Know exactly what you want? Skip the menu:**

```bash
python ascii.py dragon.png --width 120 --charset blocks --copy
```

<div align="center">

| Flag | Description | Default |
|---|---|---|
| `--menu` | force the interactive menu even if an image is given | off |
| `--width` | output width in characters, or `auto` to fit your terminal | `100` |
| `--charset` | `default` · `blocks` · `binary` · `detailed` | `default` |
| `--block` | solid `█` blocks instead of a gradient | off |
| `--invert` | invert brightness mapping | off |
| `--no-color` | plain grayscale, no ANSI color | off |
| `--tint` | recolor the art with one hex color, e.g. `00ffff` | none |
| `--alpha-threshold` | alpha cutoff for transparency (0–255) | `10` |
| `--copy` | copy the plain ASCII art to your clipboard | off |
| `--stats` | print image size / output size / transparency info | off |
| `--animate` | play an animated GIF/WEBP frame-by-frame in-terminal | off |
| `--fps` | fixed playback speed for `--animate` | native timing |
| `--loops` | times to loop `--animate` (`0` = forever) | `1` |
| `--export` | also save as `txt`, `png`, or `html` | none |
| `--out` | output file path | `<name>_ascii.<ext>` |
| `--font-size` | font size for `png`/`html` export | `12` |

</div>
<br>

## Examples

```bash
python ascii.py                                          # menu + file picker, zero flags
python ascii.py dragon.png --width auto --tint 00ffff
python ascii.py dragon.png --block --width 80
python ascii.py dragon.png --export html --out dragon.html
python ascii.py dance.gif --animate --fps 12 --loops 0
python ascii.py *.png --no-color --export txt
```

## How it works

1. no image given → opens a GUI file picker (zenity/yad/wofi/rofi), then a quick menu for size, charset, color, and export
2. loads the image, checks for real transparency
3. resizes to your target width, correcting for character aspect ratio
4. maps each pixel's brightness to a character, colored with its original RGB via truecolor ANSI codes
5. transparent pixels render as blank space, keeping the subject's shape
6. for `--animate`, each frame of the GIF/WEBP is processed the same way and streamed to the terminal in sequence

<div align="center">
<sub>needs a truecolor terminal (kitty, alacritty, iTerm2, Windows Terminal, etc.) for the color output</sub>
</div>