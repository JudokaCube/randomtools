<div align="center">

# random ass tools

**random tools no one asked for**

![Python](https://img.shields.io/badge/Python-000000?style=for-the-badge&logo=python&logoColor=00ffff)
![Pillow](https://img.shields.io/badge/Pillow-000000?style=for-the-badge&logo=python&logoColor=00ffff)

</div>
<br>

i was bored, decided to make an ascii converter, and then decided to make all of these random tools, enjoy them!

```
      ┌────────────────┐
     ╱│               ╱│
    ╱ │              ╱ │
   ┌────────────────┐  │
   │  │             │  │
   │  │             │  │
   │  │             │  │
   │  └─────────────│──┘
   │ ╱              │ ╱
   │╱               │╱
   └────────────────┘
```
<br>

## Install

```bash
pip install -r requirements.txt
```

Then just keep `tool.py` wherever's convenient and run it with `python`. No setup beyond that, works the same on Linux, macOS, and Windows.

```bash
python tool.py
```

That drops you into a menu — pick a number, answer whatever it asks, and it runs the tool. When it's done it puts you right back at the menu so you can run something else, or pick the exit option when you're actually done. If you drag a file onto the script (or pass its path as the one argument), it'll jump straight to the right tool with that file already loaded.

## The tools

| | |
|---|---|
| **`ascii`** | image to colored ASCII art. Transparent backgrounds keep their shape, GIFs play frame by frame. |
| **`palette`** | pulls the dominant colors out of an image, prints them as swatches or exports to CSS/JSON/PNG. |
| **`waveform`** | turns a `.wav` into a waveform, either a compact sparkline or the full mirrored view. |
| **`base64`** | text or a file to base64, and back. Decoding to binary works too, not just text. |
| **`morse`** | text to morse and back, in case you ever need that. |
| **`qr`** | text or a URL to a QR code, drawn right in the terminal. |
| **`passgen`** | spits out a password or a memorable passphrase, and tells you honestly how strong it is. |
| **`dice`** | rolls dice using real notation — `2d6`, `d20`, `4d6+2`, whatever. |
| **`sysinfo`** | a tiny fastfetch clone. OS, CPU, memory, uptime, next to a little ASCII logo. |

## A couple extra stuff

- `qr` needs one extra package beyond Pillow: `qrcode[pil]`, already in `requirements.txt`.
- `waveform` only reads `.wav`. Got something else? Convert it first — `ffmpeg -i song.mp3 song.wav` does it.
- The clipboard prompts (`passgen`, `base64`, `morse`) try to use your system clipboard automatically. `pyperclip` (in `requirements.txt`) handles this on every platform; on Linux without it, install `wl-copy`, `xclip`, or `xsel`.
- Colored output assumes a truecolor terminal — kitty, alacritty, iTerm2, Windows Terminal, that kind of thing. If your terminal's older, colors might look off.
