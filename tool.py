"""
random ass tools — a small multitool for your terminal.

Tools:
    ascii      image  -> ASCII art
    palette    image  -> dominant color palette
    waveform   .wav   -> waveform art
    base64     text/file -> base64 encode or decode
    morse      text  <-> morse code
    qr         text   -> QR code
    passgen    ->  password / passphrase generator
    dice       ->  roll dice with custom notation
    sysinfo    ->  system info, fastfetch style

There are no flags. Run `python tool.py` and pick a number — the menu
walks you through everything from there, then drops you back at the
menu when you're done so you can run something else (or pick exit).
Drag a file onto the script (or pass its path as a single argument)
to skip straight to its tool.
"""

import array
import base64 as b64
import colorsys
import getpass
import json
import math
import os
import platform
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont, ImageSequence, UnidentifiedImageError

RESET = "\033[0m"
CYAN = "\033[36m"
BOLD_CYAN = "\033[1;36m"
DIM_CYAN = "\033[2;36m"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
AUDIO_EXTS = {".wav"}


# ══════════════════════════════════════════════════════════════════════════
# shared helpers — used by more than one tool
# ══════════════════════════════════════════════════════════════════════════

def enable_ansi_on_windows():
    """Turn on ANSI/VT100 escape processing in classic cmd.exe (no-op elsewhere)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def find_monospace_font() -> str | None:
    """Locate a decent monospace TTF/TTC for image export, per platform."""
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates += ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf"]
    elif sys.platform.startswith("win"):
        import os

        windir = os.environ.get("WINDIR", r"C:\Windows")
        candidates += [str(Path(windir) / "Fonts" / "consola.ttf"), str(Path(windir) / "Fonts" / "cour.ttf")]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def copy_to_clipboard(text: str) -> bool:
    """Try several clipboard mechanisms depending on platform. Returns success."""
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        pass

    if sys.platform == "darwin":
        candidates = [["pbcopy"]]
    elif sys.platform.startswith("win"):
        candidates = [["clip"]]
    else:
        candidates = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]

    for cmd in candidates:
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


def parse_hex_color(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        sys.exit(f"error: '{s}' isn't a valid hex color, expected format like ff8800")
    try:
        return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        sys.exit(f"error: '{s}' isn't a valid hex color, expected format like ff8800")


def hex_of(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def resolve_width(width_arg: str) -> int:
    if width_arg == "auto":
        return max(20, shutil.get_terminal_size((100, 24)).columns)
    try:
        return int(width_arg)
    except ValueError:
        sys.exit(f"error: --width must be a number or 'auto', got '{width_arg}'")


def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def list_files(base_dirs, exts):
    files = []
    for d in base_dirs:
        p = Path(d).expanduser()
        if not p.exists():
            continue
        try:
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in exts:
                    files.append(f)
        except PermissionError:
            continue
    return files


def pick_file_gui(exts=IMAGE_EXTS, prompt="select a file"):
    """Best native file picker for the current OS, with a Tk fallback everywhere."""
    if sys.platform == "darwin":
        script = f'POSIX path of (choose file with prompt "{prompt}")'
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=120)
            out = result.stdout.strip()
            if result.returncode == 0 and out:
                return out
            return None
        except Exception:
            pass

    elif not sys.platform.startswith("win"):
        for tool, args in (
            ("zenity", ["--file-selection", f"--title={prompt}"]),
            ("yad", ["--file-selection", f"--title={prompt}"]),
        ):
            if shutil.which(tool):
                try:
                    result = subprocess.run([tool, *args], capture_output=True, text=True, timeout=120)
                    out = result.stdout.strip()
                    if result.returncode == 0 and out:
                        return out
                    return None
                except Exception:
                    continue

        for tool, args in (
            ("wofi", ["--dmenu", "--prompt", prompt]),
            ("rofi", ["-dmenu", "-p", prompt]),
        ):
            if shutil.which(tool):
                candidates = list_files([Path.home() / "Pictures", Path.home() / "Downloads", Path.cwd()], exts)
                if not candidates:
                    continue
                listing = "\n".join(str(c) for c in sorted(candidates))
                try:
                    result = subprocess.run([tool, *args], input=listing, capture_output=True, text=True, timeout=120)
                    sel = result.stdout.strip()
                    if sel:
                        return sel
                except Exception:
                    continue

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        pattern = "*" + " *".join(sorted(exts)) if exts else "*.*"
        path = filedialog.askopenfilename(
            title=prompt, filetypes=[("Files", pattern), ("All files", "*.*")]
        )
        root.destroy()
        return path or None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
# ascii — image to ASCII art
# ══════════════════════════════════════════════════════════════════════════

ASCII_CHARSETS = {
    "default": " .:-=+*#%@",
    "blocks": " ░▒▓█",
    "binary": " #",
    "detailed": " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
}

ASCII_SIZE_PRESETS = {
    "1": ("small", "60"),
    "2": ("medium", "100"),
    "3": ("large", "160"),
    "4": ("huge", "220"),
    "5": ("auto (fit terminal)", "auto"),
}


def ascii_load_image(path: str) -> tuple[Image.Image, bool]:
    img_path = Path(path)
    if not img_path.exists():
        sys.exit(f"error: file not found: {path}")
    try:
        img = Image.open(img_path)
        img.load()
    except UnidentifiedImageError:
        sys.exit(f"error: '{path}' is not a recognizable image file.")
    except Exception as e:
        sys.exit(f"error: could not open image ({e})")
    rgba = img.convert("RGBA")
    alpha_min, _ = rgba.getchannel("A").getextrema()
    return rgba, alpha_min < 255


def ascii_load_animation_frames(path: str):
    img = Image.open(path)
    n_frames = getattr(img, "n_frames", 1)
    if n_frames <= 1:
        return None
    frames = []
    for frame in ImageSequence.Iterator(img):
        duration = frame.info.get("duration", 100)
        frames.append((frame.convert("RGBA"), duration))
    return frames


def ascii_resize_image(img: Image.Image, new_width: int, char_aspect: float = 0.55) -> Image.Image:
    w, h = img.size
    ratio = h / w
    new_height = max(1, int(new_width * ratio * char_aspect))
    return img.resize((new_width, new_height), Image.LANCZOS)


def ascii_brightness(r: int, g: int, b: int) -> float:
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ascii_char_for_brightness(value: float, charset: str, invert: bool) -> str:
    chars = charset[::-1] if invert else charset
    idx = int((value / 255) * (len(chars) - 1))
    return chars[idx]


def ascii_build_grid(img, charset_name, invert, alpha_threshold, block_char, tint=None):
    charset = ASCII_CHARSETS[charset_name]
    pixels = img.load()
    w, h = img.size
    grid = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < alpha_threshold:
                row.append((" ", None))
                continue
            val = ascii_brightness(r, g, b)
            ch = block_char if block_char else ascii_char_for_brightness(val, charset, invert)
            if tint:
                scale = val / 255
                r, g, b = (int(c * scale) for c in tint)
            row.append((ch, (r, g, b)))
        grid.append(row)
    return grid


def ascii_render_terminal(grid, color: bool) -> str:
    lines = []
    for row in grid:
        parts = []
        for ch, rgb in row:
            if rgb is None or not color:
                parts.append(ch)
            else:
                r, g, b = rgb
                parts.append(f"\033[38;2;{r};{g};{b}m{ch}{RESET}")
        lines.append("".join(parts))
    return "\n".join(lines)


def ascii_render_plain(grid) -> str:
    return "\n".join("".join(ch for ch, _ in row) for row in grid)


def ascii_export_png(grid, out_path, font_size=12, bg=(0, 0, 0, 0)):
    font_path = find_monospace_font()
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    bbox = font.getbbox("A")
    char_w = bbox[2] - bbox[0] + 1
    char_h = int(font_size * 1.15)
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    canvas = Image.new("RGBA", (cols * char_w, rows * char_h), bg)
    draw = ImageDraw.Draw(canvas)
    for y, row in enumerate(grid):
        for x, (ch, rgb) in enumerate(row):
            if rgb is None or ch == " ":
                continue
            draw.text((x * char_w, y * char_h), ch, font=font, fill=rgb + (255,))
    canvas.save(out_path)


def ascii_export_html(grid, out_path, font_size=14, bg="#0d1117"):
    lines = []
    for row in grid:
        spans = []
        for ch, rgb in row:
            char_html = "&nbsp;" if ch == " " else ch
            if rgb is None:
                spans.append(char_html)
            else:
                r, g, b = rgb
                spans.append(f'<span style="color:rgb({r},{g},{b})">{char_html}</span>')
        lines.append("".join(spans))
    body = "<br>\n".join(lines)
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ASCII Art</title>
<style>
  body {{ background:{bg}; margin:0; padding:24px; }}
  .ascii {{ font-family:'Consolas','Menlo','DejaVu Sans Mono','Courier New',monospace;
            font-size:{font_size}px; line-height:1; white-space:pre; }}
</style></head>
<body><div class="ascii">{body}</div></body></html>"""
    Path(out_path).write_text(html, encoding="utf-8")


def ascii_play_animation(frames, width, charset_name, invert, alpha_threshold, block_char, color, fps, loops, tint):
    fixed_interval = (1 / fps) if fps else None
    played = 0
    try:
        while loops == 0 or played < loops:
            for frame_img, duration_ms in frames:
                resized = ascii_resize_image(frame_img, width)
                grid = ascii_build_grid(resized, charset_name, invert, alpha_threshold, block_char, tint)
                sys.stdout.write("\033[H\033[J")
                sys.stdout.write(ascii_render_terminal(grid, color))
                sys.stdout.flush()
                time.sleep(fixed_interval if fixed_interval else max(duration_ms, 20) / 1000)
            played += 1
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)


def ascii_process_image(path, args):
    img, has_transparency = ascii_load_image(path)
    if not has_transparency:
        print(f"note: no transparency detected in '{path}', rendering the full frame.", file=sys.stderr)
    width = resolve_width(args.width)
    resized = ascii_resize_image(img, width)
    block_char = "█" if args.block else None
    tint = parse_hex_color(args.tint) if args.tint else None
    grid = ascii_build_grid(resized, args.charset, args.invert, args.alpha_threshold, block_char, tint)
    print(ascii_render_terminal(grid, color=not args.no_color))

    if args.stats:
        rows, cols = len(grid), len(grid[0]) if grid else 0
        print(
            f"stats: {path}\n  source size     {img.size[0]}x{img.size[1]}px\n"
            f"  output size     {cols}x{rows} chars\n  transparency    {'yes' if has_transparency else 'no'}",
            file=sys.stderr,
        )

    if args.export:
        stem = Path(path).stem
        out_path = args.out or f"{stem}_ascii.{args.export}"
        if args.export == "txt":
            Path(out_path).write_text(ascii_render_plain(grid), encoding="utf-8")
        elif args.export == "html":
            ascii_export_html(grid, out_path, font_size=args.font_size)
        else:
            ascii_export_png(grid, out_path, font_size=args.font_size)
        print(f"saved to {out_path}", file=sys.stderr)

    if args.copy:
        ok = copy_to_clipboard(ascii_render_plain(grid))
        print("copied to clipboard" if ok else "warning: no clipboard tool found.", file=sys.stderr)


def ascii_interactive_menu(preset_path=None):
    path = preset_path
    if not path:
        path = pick_file_gui(IMAGE_EXTS, "select an image")
    if not path:
        path = ask("image path (or drag & drop the file here)")
    while not path or not Path(path).expanduser().exists():
        path = ask("couldn't find that file — image path")
    path = str(Path(path).expanduser())

    print("\nsize:")
    for key, (label, _) in ASCII_SIZE_PRESETS.items():
        print(f"  {key}) {label}")
    size_choice = ask("choose a size", "2")
    width = ASCII_SIZE_PRESETS.get(size_choice, (None, size_choice if size_choice.isdigit() else "100"))[1]

    print("\ncharset:")
    keys = list(ASCII_CHARSETS.keys())
    for i, k in enumerate(keys, 1):
        print(f"  {i}) {k}")
    cs_choice = ask("choose a charset", "1")
    charset = keys[int(cs_choice) - 1] if cs_choice.isdigit() and 1 <= int(cs_choice) <= len(keys) else "default"

    color = ask("color output? (y/n)", "y").lower().startswith("y")
    block = ask("use solid blocks instead of gradient? (y/n)", "n").lower().startswith("y")
    tint_in = ask("tint hex color (blank for none, e.g. 00ffff)", "")
    tint = tint_in if tint_in else None

    animate = False
    if Path(path).suffix.lower() in (".gif", ".webp"):
        animate = ask("this might be animated — play as animation? (y/n)", "n").lower().startswith("y")

    export = out = None
    copy = False
    if not animate:
        export_choice = ask("export to a file? (n/txt/png/html)", "n").lower()
        if export_choice in ("txt", "png", "html"):
            export = export_choice
            out = ask("output filename", f"{Path(path).stem}_ascii.{export}")
        copy = ask("copy to clipboard? (y/n)", "n").lower().startswith("y")

    print()
    args = SimpleNamespace(
        width=width, charset=charset, block=block, invert=False, no_color=not color,
        tint=tint, alpha_threshold=10, export=export, out=out, font_size=12, copy=copy,
        stats=False, animate=animate, fps=0, loops=1,
    )
    if animate:
        frames = ascii_load_animation_frames(path)
        if frames is None:
            print("note: not actually animated, rendering a single frame instead.\n", file=sys.stderr)
            ascii_process_image(path, args)
        else:
            w = resolve_width(args.width)
            block_char = "█" if args.block else None
            tint_rgb = parse_hex_color(args.tint) if args.tint else None
            print("playing — press Ctrl+C to stop\n")
            ascii_play_animation(frames, w, args.charset, args.invert, args.alpha_threshold, block_char, color, args.fps, args.loops, tint_rgb)
    else:
        ascii_process_image(path, args)


# ══════════════════════════════════════════════════════════════════════════
# palette — dominant colors from an image
# ══════════════════════════════════════════════════════════════════════════

def palette_extract(img: Image.Image, n: int, sort_mode: str):
    small = img.convert("RGB").copy()
    small.thumbnail((200, 200))
    quant = small.quantize(colors=max(n, 2), method=Image.MEDIANCUT)
    pal = quant.getpalette()
    counts = sorted(quant.getcolors(), reverse=True)
    colors = [tuple(pal[idx * 3 : idx * 3 + 3]) for _, idx in counts[:n]]
    if sort_mode == "hue":
        colors.sort(key=lambda c: colorsys.rgb_to_hsv(*(v / 255 for v in c))[0])
    elif sort_mode == "brightness":
        colors.sort(key=lambda c: ascii_brightness(*c))
    return colors


def palette_print(colors, no_color):
    for r, g, b in colors:
        h = hex_of((r, g, b))
        if no_color:
            print(h)
        else:
            print(f"\033[48;2;{r};{g};{b}m        {RESET}  {h}   rgb({r:>3},{g:>3},{b:>3})")


def palette_export(colors, fmt, out_path):
    if fmt == "json":
        data = [{"hex": hex_of(c), "rgb": list(c)} for c in colors]
        Path(out_path).write_text(json.dumps(data, indent=2))
    elif fmt == "css":
        lines = [":root {"] + [f"  --color-{i}: {hex_of(c)};" for i, c in enumerate(colors, 1)] + ["}"]
        Path(out_path).write_text("\n".join(lines))
    elif fmt == "txt":
        Path(out_path).write_text("\n".join(hex_of(c) for c in colors))
    else:  # png
        sw = 120
        canvas = Image.new("RGB", (sw * len(colors), sw), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        for i, c in enumerate(colors):
            draw.rectangle([i * sw, 0, (i + 1) * sw, sw], fill=c)
        canvas.save(out_path)
    print(f"saved to {out_path}", file=sys.stderr)


def cmd_palette(args):
    img = Image.open(args.image)
    colors = palette_extract(img, args.colors, args.sort)
    palette_print(colors, args.no_color)
    if args.export:
        out = args.out or f"{Path(args.image).stem}_palette.{args.export}"
        palette_export(colors, args.export, out)


# ══════════════════════════════════════════════════════════════════════════
# waveform — .wav file to waveform art
# ══════════════════════════════════════════════════════════════════════════

WAVEFORM_BARS = " ▁▂▃▄▅▆▇█"


def waveform_read_samples(path, channel):
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 1:
        samples = array.array("h", (b - 128 for b in raw))
    elif sampwidth == 2:
        samples = array.array("h", raw)
    elif sampwidth == 4:
        samples = array.array("i", raw)
    else:
        sys.exit(f"error: unsupported sample width ({sampwidth} bytes)")

    if n_channels > 1:
        if channel == "left":
            samples = samples[0::n_channels]
        elif channel == "right":
            samples = samples[1::n_channels] if n_channels > 1 else samples
        else:
            samples = array.array("d", (
                sum(samples[i : i + n_channels]) / n_channels for i in range(0, len(samples) - n_channels + 1, n_channels)
            ))
    return samples


def waveform_downsample(samples, width):
    n = len(samples)
    if n == 0:
        return [0.0] * width
    chunk = max(1, n // width)
    peaks = []
    for i in range(width):
        seg = samples[i * chunk : min(n, (i + 1) * chunk)]
        peaks.append(max((abs(s) for s in seg), default=0))
    m = max(peaks) or 1
    return [p / m for p in peaks]


def waveform_render_line(peaks, color_rgb):
    line = "".join(WAVEFORM_BARS[int(p * (len(WAVEFORM_BARS) - 1))] for p in peaks)
    return f"\033[38;2;{color_rgb[0]};{color_rgb[1]};{color_rgb[2]}m{line}{RESET}" if color_rgb else line


def waveform_render_full(peaks, height, color_rgb):
    half = max(1, height // 2)
    grid = [[" "] * len(peaks) for _ in range(half * 2)]
    for x, p in enumerate(peaks):
        bar = max(1, round(p * half))
        for y in range(bar):
            grid[half - 1 - y][x] = "█"
            grid[half + y][x] = "█"
    lines = ["".join(row) for row in grid]
    if color_rgb:
        r, g, b = color_rgb
        lines = [f"\033[38;2;{r};{g};{b}m{l}{RESET}" for l in lines]
    return "\n".join(lines)


def waveform_export(peaks, fmt, out_path, color_hex):
    if fmt == "txt":
        Path(out_path).write_text("".join(WAVEFORM_BARS[int(p * (len(WAVEFORM_BARS) - 1))] for p in peaks))
    elif fmt == "svg":
        width, height = 800, 200
        bar_w = width / len(peaks)
        mid = height / 2
        rects = []
        for i, p in enumerate(peaks):
            h = max(2, p * height)
            rects.append(f'<rect x="{i*bar_w:.2f}" y="{mid-h/2:.2f}" width="{bar_w*0.7:.2f}" height="{h:.2f}" fill="#{color_hex}"/>')
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
            f'<rect width="100%" height="100%" fill="#0d1117"/>{"".join(rects)}</svg>'
        )
        Path(out_path).write_text(svg)
    else:  # png
        width, height = 900, 240
        canvas = Image.new("RGB", (width, height), (13, 17, 23))
        draw = ImageDraw.Draw(canvas)
        rgb = parse_hex_color(color_hex)
        bar_w = width / len(peaks)
        mid = height / 2
        for i, p in enumerate(peaks):
            h = max(2, p * height)
            x0 = i * bar_w
            draw.rectangle([x0, mid - h / 2, x0 + bar_w * 0.7, mid + h / 2], fill=rgb)
        canvas.save(out_path)
    print(f"saved to {out_path}", file=sys.stderr)


def cmd_waveform(args):
    if Path(args.audio).suffix.lower() not in AUDIO_EXTS:
        sys.exit("error: only .wav files are supported. Convert first, e.g.: ffmpeg -i in.mp3 out.wav")
    samples = waveform_read_samples(args.audio, args.channel)
    width = resolve_width(args.width) if not args.full else min(resolve_width(args.width), 200)
    peaks = waveform_downsample(samples, width)
    color_rgb = None if args.no_color else parse_hex_color(args.color)

    if args.full:
        print(waveform_render_full(peaks, args.height, color_rgb))
    else:
        print(waveform_render_line(peaks, color_rgb))

    if args.export:
        out = args.out or f"{Path(args.audio).stem}_waveform.{args.export}"
        waveform_export(peaks, args.export, out, args.color)


# ══════════════════════════════════════════════════════════════════════════
# passgen — password / passphrase generator
# ══════════════════════════════════════════════════════════════════════════

_WORDLIST_RAW = """
tiger lion wolf eagle otter panda koala zebra rhino camel llama moose beaver
badger falcon heron ferret gecko iguana walrus dolphin whale shark salmon
trout sparrow robin raven crow swan goose duck hawk owl fox bear deer elk
hare rabbit mouse squirrel mountain river ocean forest desert valley canyon
glacier volcano island meadow prairie tundra jungle reef cave cliff
waterfall storm thunder lightning rainbow breeze cloud frost snow rain
sunrise sunset dawn dusk twilight horizon comet meteor aurora nebula galaxy
crimson amber violet indigo scarlet emerald sapphire coral turquoise
magenta lavender ivory obsidian copper bronze silver golden charcoal maroon
teal anchor lantern compass telescope hammer chisel ladder bucket kettle
blanket pillow mirror candle bottle basket barrel wagon carriage bicycle
umbrella satchel canteen locket buckle ribbon thread needle spindle loom
anvil forge bellows quiver arrow shield helmet gauntlet cloak pepper
cinnamon vanilla saffron honey walnut almond hazelnut chestnut apricot
mango papaya coconut pineapple pomegranate fig olive pretzel biscuit muffin
pancake waffle noodle dumpling lentil oatmeal pumpkin squash artichoke
brave quiet swift silent wild fierce gentle clever bold vivid rustic
ancient frozen molten hollow rugged sturdy nimble radiant somber tranquil
restless daring humble jagged velvet subtle vibrant crisp lush murky dusty
glossy pristine weathered mellow feral serene wander drift kindle ignite
whisper murmur echo glide soar plunge climb gather harvest sculpt weave
carve etch polish mend build harbor citadel outpost sanctuary hamlet
village orchard vineyard quarry foundry lighthouse observatory monastery
fortress bazaar market plaza garden courtyard chapel tavern cottage cabin
bridge tunnel causeway pier dock wharf journey voyage odyssey legend saga
riddle puzzle mystery secret treasure relic artifact rune sigil map chart
scroll ledger tome chronicle epic ballad melody rhythm harmony shadow ember
spark flame ash smoke mist fog willow birch cedar maple aspen sequoia
bamboo fern moss lichen thistle clover heather ivy blossom petal thorn
bramble orchid tulip daisy poppy jasmine lilac magnolia peony marigold
granite marble quartz slate basalt limestone sandstone pebble boulder
gravel clay loam silt driftwood timber plank beam rafter shingle brick
mortar hinge latch bolt screw nail wrench pulley gear piston valve
turbine rotor propeller rudder mast sail keel hull deck cargo freight
caravan expedition pilgrimage frontier wilderness summit ridge plateau
basin delta estuary lagoon marsh swamp bog dune oasis savanna steppe
archway pavilion terrace balcony rampart parapet turret spire dome
mosaic fresco tapestry embroidery lattice trellis fountain courtyard
lantern torch beacon ember bonfire hearth chimney furnace kiln crucible
alloy ingot ore vein seam crystal prism lens prism spectrum photon
electron neutron atom molecule enzyme cell organism spore fungus algae
plankton coral kelp anemone barnacle starfish urchin seahorse manta
albatross condor osprey kestrel puffin pelican flamingo peacock parrot
toucan hummingbird woodpecker cuckoo nightingale lark finch wren martin
swallow tern gull cormorant heron egret ibis stork crane bittern
""".split()

WORDLIST = sorted(set(_WORDLIST_RAW))


def passgen_entropy_bits(pool_size: int, count: int) -> float:
    return count * math.log2(pool_size) if pool_size > 1 else 0.0


def passgen_strength_label(bits: float) -> str:
    if bits < 40:
        return "weak"
    if bits < 60:
        return "reasonable"
    if bits < 80:
        return "strong"
    return "very strong"


def passgen_phrase(n_words, separator, capitalize, add_number, add_symbol):
    rng = secrets.SystemRandom()
    words = rng.sample(WORDLIST, min(n_words, len(WORDLIST)))
    if n_words > len(WORDLIST):
        words += [rng.choice(WORDLIST) for _ in range(n_words - len(WORDLIST))]
    if capitalize:
        words = [w.capitalize() for w in words]
    parts = words[:]
    if add_number:
        parts.append(str(secrets.randbelow(100)))
    if add_symbol:
        parts.append(secrets.choice("!@#$%&*?"))
    return separator.join(parts), passgen_entropy_bits(len(WORDLIST), n_words)


def passgen_random(length, use_digits, use_symbols):
    pool = string.ascii_letters
    if use_digits:
        pool += string.digits
    if use_symbols:
        pool += "!@#$%^&*()-_=+"
    pw = "".join(secrets.choice(pool) for _ in range(length))
    return pw, passgen_entropy_bits(len(pool), length)


def cmd_passgen(args):
    results = []
    for _ in range(args.count):
        if args.mode == "random":
            results.append(passgen_random(args.length, args.digits, args.symbols))
        else:
            results.append(passgen_phrase(args.words, args.separator, args.capitalize, args.digits, args.symbols))

    for pw, bits in results:
        print(f"{pw}    ({bits:.0f} bits — {passgen_strength_label(bits)})")

    if args.copy:
        ok = copy_to_clipboard(results[-1][0])
        print("copied to clipboard" if ok else "warning: no clipboard tool found.", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════
# base64 — text / file to base64, and back
# ══════════════════════════════════════════════════════════════════════════

def cmd_base64(args):
    if args.mode == "encode":
        data = Path(args.file).read_bytes() if args.file else args.text.encode("utf-8")
        result = b64.b64encode(data).decode("ascii")
        print(result)
    else:
        raw = Path(args.file).read_text().strip() if args.file else args.text.strip()
        try:
            decoded = b64.b64decode(raw)
        except Exception as e:
            sys.exit(f"error: couldn't decode that as base64 ({e})")
        try:
            result = decoded.decode("utf-8")
            print(result)
        except UnicodeDecodeError:
            if not args.out:
                sys.exit("error: decoded data isn't valid text — rerun and give an output filename to save it as binary")
            Path(args.out).write_bytes(decoded)
            print(f"saved decoded binary data to {args.out}", file=sys.stderr)
            return

    if args.copy:
        ok = copy_to_clipboard(result)
        print("copied to clipboard" if ok else "warning: no clipboard tool found.", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════
# dice — customizable dice roller
# ══════════════════════════════════════════════════════════════════════════

DICE_PATTERN = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$")


def dice_roll(spec: str):
    """Parse and roll a spec like '2d6', 'd20', or '4d6+2'. Returns None if unparsable."""
    m = DICE_PATTERN.match(spec.strip().lower().replace(" ", ""))
    if not m:
        return None
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    modifier = int(m.group(3)) if m.group(3) else 0
    if not (1 <= count <= 100) or sides < 2:
        return None
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    return rolls, modifier, sum(rolls) + modifier


def cmd_dice(args):
    for spec in args.specs:
        result = dice_roll(spec)
        if result is None:
            print(f"error: couldn't parse '{spec}' — try something like 2d6, d20, or 4d6+2", file=sys.stderr)
            continue
        rolls, modifier, total = result
        rolls_str = " + ".join(str(r) for r in rolls) if len(rolls) > 1 else str(rolls[0])
        if modifier:
            sign = "+" if modifier > 0 else "-"
            print(f"{spec:<10} [{rolls_str}] {sign} {abs(modifier)}  =  {BOLD_CYAN}{total}{RESET}")
        else:
            print(f"{spec:<10} [{rolls_str}]  =  {BOLD_CYAN}{total}{RESET}")


# ══════════════════════════════════════════════════════════════════════════
# morse — text to morse code, and back
# ══════════════════════════════════════════════════════════════════════════

MORSE_TABLE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    '"': ".-..-.", "$": "...-..-", "@": ".--.-.",
}
MORSE_REVERSE = {v: k for k, v in MORSE_TABLE.items()}


def morse_encode(text: str) -> str:
    words = text.upper().split(" ")
    encoded = []
    for word in words:
        letters = [MORSE_TABLE[c] for c in word if c in MORSE_TABLE]
        encoded.append(" ".join(letters))
    return " / ".join(encoded)


def morse_decode(code: str) -> str:
    words = code.strip().split(" / ")
    decoded = []
    for word in words:
        letters = [MORSE_REVERSE.get(sym, "") for sym in word.split(" ") if sym]
        decoded.append("".join(letters))
    return " ".join(decoded)


def cmd_morse(args):
    result = morse_encode(args.text) if args.mode == "encode" else morse_decode(args.text)
    print(result)
    if args.copy:
        ok = copy_to_clipboard(result)
        print("copied to clipboard" if ok else "warning: no clipboard tool found.", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════
# sysinfo — a mini fastfetch, with a simple ascii logo
# ══════════════════════════════════════════════════════════════════════════

SYSINFO_LOGO = [
    "{C}╭──────────────────╮{R}",
    "{C}│{R} {D}●  ●  ●{R}          {C}│{R}",
    "{C}├──────────────────┤{R}",
    "{C}│{R}                  {C}│{R}",
    "{C}│{R}  {B}▁▂▃▅▇█{R}          {C}│{R}",
    "{C}│{R}                  {C}│{R}",
    "{C}│{R}  {B}$ _{R}             {C}│{R}",
    "{C}│{R}                  {C}│{R}",
    "{C}│{R}                  {C}│{R}",
    "{C}╰──────────────────╯{R}",
]


def sysinfo_format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = [f"{days}d"] if days else []
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def sysinfo_uptime() -> str:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/uptime") as f:
                return sysinfo_format_duration(float(f.readline().split()[0]))
        elif sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5)
            m = re.search(r"sec = (\d+)", out.stdout)
            if m:
                return sysinfo_format_duration(time.time() - int(m.group(1)))
        elif sys.platform.startswith("win"):
            import ctypes

            return sysinfo_format_duration(ctypes.windll.kernel32.GetTickCount64() / 1000)
    except Exception:
        pass
    return "unknown"


def sysinfo_memory() -> str:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo") as f:
                meminfo = dict(line.split(":", 1) for line in f if ":" in line)
            total_kb = int(meminfo["MemTotal"].split()[0])
            avail_kb = int(meminfo.get("MemAvailable", "0 kB").split()[0])
            return f"{(total_kb - avail_kb) // 1024}MiB / {total_kb // 1024}MiB"
        elif sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            return f"{int(out.stdout.strip()) // (1024 ** 2)}MiB total"
        elif sys.platform.startswith("win"):
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemStatus()
            stat.dwLength = ctypes.sizeof(MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            used = stat.ullTotalPhys - stat.ullAvailPhys
            return f"{used // (1024 ** 2)}MiB / {stat.ullTotalPhys // (1024 ** 2)}MiB"
    except Exception:
        pass
    return "unknown"


def cmd_sysinfo():
    user = getpass.getuser()
    host = socket.gethostname()
    header = f"{user}@{host}"

    rows = [
        (f"{BOLD_CYAN}{user}{RESET}@{BOLD_CYAN}{host}{RESET}", ""),
        (f"{CYAN}{'-' * len(header)}{RESET}", ""),
        ("os", f"{platform.system()} {platform.release()}"),
        ("arch", platform.machine() or "unknown"),
        ("python", platform.python_version()),
        ("shell", Path(os.environ.get("SHELL", os.environ.get("COMSPEC", "unknown"))).name),
        ("term", os.environ.get("TERM") or os.environ.get("TERM_PROGRAM") or "unknown"),
        ("cpu", f"{platform.processor() or platform.machine()} ({os.cpu_count()} cores)"),
        ("memory", sysinfo_memory()),
        ("uptime", sysinfo_uptime()),
    ]
    label_w = max(len(label) for label, _ in rows[2:])
    lines = [rows[0][0], rows[1][0]] + [
        f"{CYAN}{label.ljust(label_w)}{RESET}  {value}" for label, value in rows[2:]
    ]

    logo = [line.format(D=DIM_CYAN, C=CYAN, B=BOLD_CYAN, R=RESET) for line in SYSINFO_LOGO]
    height = max(len(logo), len(lines))
    print()
    for i in range(height):
        logo_line = logo[i] if i < len(logo) else ""
        info_line = lines[i] if i < len(lines) else ""
        print(f"{logo_line}   {info_line}")
    print()


# ══════════════════════════════════════════════════════════════════════════
# qr — text / URL to QR code
# ══════════════════════════════════════════════════════════════════════════

def qr_render_terminal(matrix, invert):
    if invert:
        matrix = [[not v for v in row] for row in matrix]
    lines = []
    h = len(matrix)
    for y in range(0, h, 2):
        top = matrix[y]
        bottom = matrix[y + 1] if y + 1 < h else [False] * len(top)
        line = []
        for t, b in zip(top, bottom):
            line.append("█" if t and b else "▀" if t else "▄" if b else " ")
        lines.append("".join(line))
    return "\n".join(lines)


def cmd_qr(args):
    try:
        import qrcode
    except ImportError:
        sys.exit("the qr tool needs the 'qrcode' package — install it with: pip install qrcode[pil]")

    qr = qrcode.QRCode(border=2)
    qr.add_data(args.text)
    qr.make(fit=True)
    print(qr_render_terminal(qr.get_matrix(), args.invert))

    if args.export == "png":
        out = args.out or "qr.png"
        qr.make_image(fill_color="black", back_color="white").save(out)
        print(f"saved to {out}", file=sys.stderr)
    elif args.export == "svg":
        import qrcode.image.svg

        out = args.out or "qr.svg"
        qrcode.make(args.text, image_factory=qrcode.image.svg.SvgImage).save(out)
        print(f"saved to {out}", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════
# interactive menu (the only way in — no subcommands, no flags)
# ══════════════════════════════════════════════════════════════════════════

TOOLS = [
    ("ascii", "image  → ASCII art"),
    ("palette", "image  → dominant color palette"),
    ("waveform", "wav    → waveform art"),
    ("base64", "text/file → base64 encode / decode"),
    ("morse", "text   ↔ morse code"),
    ("qr", "text   → QR code"),
    ("passgen", "generate a password / passphrase"),
    ("dice", "roll dice with custom notation"),
    ("sysinfo", "system info, fastfetch style"),
]

LOGO = [
    "      {D}┌────────────────┐{R}",
    "     {C}╱{D}│               {C}╱{D}│{R}",
    "    {C}╱ {D}│              {C}╱ {D}│{R}",
    "   {B}┌────────────────┐  {D}│{R}",
    "   {B}│  {D}│             {B}│  {D}│{R}",
    "   {B}│  {D}│             {B}│  {D}│{R}",
    "   {B}│  {D}│             {B}│  {D}│{R}",
    "   {B}│  {D}└─────────────{B}│{D}──┘{R}",
    "   {B}│ {C}╱              {B}│ {C}╱ {R}",
    "   {B}│{C}╱               {B}│{C}╱  {R}",
    "   {B}└────────────────┘   {R}",
]

TITLE = "R A N D O M   A S S   T O O L S"
TAGLINE = "random tools no one asked for"


def _box(lines, width):
    top = f"{CYAN}╭{'─' * (width - 2)}╮{RESET}"
    bottom = f"{CYAN}╰{'─' * (width - 2)}╯{RESET}"
    body = [f"{CYAN}│{RESET}{line}{CYAN}│{RESET}" for line in lines]
    return [top, *body, bottom]


def print_banner():
    term_w = shutil.get_terminal_size((80, 24)).columns
    if term_w >= 60:
        for row in LOGO:
            print(row.format(D=DIM_CYAN, C=CYAN, B=BOLD_CYAN, R=RESET))
    print()
    print(f"{BOLD_CYAN}{TITLE.center(term_w)}{RESET}")
    print(f"{DIM_CYAN}{TAGLINE.center(term_w)}{RESET}")
    print()


def print_menu():
    menu_items = TOOLS + [("exit", "quit random ass tools")]
    inner_w = max(len(desc) for _, desc in menu_items) + 18
    lines = []
    for i, (name, desc) in enumerate(menu_items, 1):
        text = f"  {BOLD_CYAN}{i}{RESET}  {name:<10}{desc}"
        pad = inner_w - len(f"  {i}  {name:<10}{desc}")
        lines.append(text + (" " * max(pad, 1)))
    for row in _box(lines, inner_w + 2):
        print(row)


def interactive_menu(preset_path=None):
    print_banner()
    print_menu()
    menu_items = TOOLS + [("exit", "quit random ass tools")]
    default_choice = "1"
    if preset_path:
        suffix = Path(preset_path).suffix.lower()
        target = "waveform" if suffix in AUDIO_EXTS else "ascii" if suffix in IMAGE_EXTS else None
        if target:
            default_choice = str(next(i for i, (nm, _) in enumerate(TOOLS, 1) if nm == target))
    choice = ask(f"\n{CYAN}which tool{RESET}", default_choice)
    idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(menu_items) else 0
    name = menu_items[idx][0]
    print()

    if name == "exit":
        print(f"{DIM_CYAN}see ya{RESET}")
        return False

    if name == "ascii":
        ascii_interactive_menu(preset_path if preset_path and Path(preset_path).suffix.lower() in IMAGE_EXTS else None)
        return True

    if name == "passgen":
        mode = ask("passphrase or random characters? (words/random)", "words")
        if mode.startswith("r"):
            length = int(ask("length", "16"))
            digits = ask("include digits? (y/n)", "y").lower().startswith("y")
            symbols = ask("include symbols? (y/n)", "n").lower().startswith("y")
            args = SimpleNamespace(mode="random", length=length, digits=digits, symbols=symbols, count=1, copy=False)
        else:
            n_words = int(ask("how many words", "4"))
            sep = ask("separator", "-")
            cap = ask("capitalize words? (y/n)", "n").lower().startswith("y")
            digits = ask("add a number? (y/n)", "y").lower().startswith("y")
            symbols = ask("add a symbol? (y/n)", "n").lower().startswith("y")
            args = SimpleNamespace(mode="words", words=n_words, separator=sep, capitalize=cap, digits=digits, symbols=symbols, count=1, copy=False)
        copy = ask("copy to clipboard? (y/n)", "n").lower().startswith("y")
        args.copy = copy
        cmd_passgen(args)
        return True

    if name == "qr":
        text = ask("text or URL to encode")
        while not text:
            text = ask("text or URL to encode")
        export_choice = ask("export? (n/png/svg)", "n").lower()
        export = export_choice if export_choice in ("png", "svg") else None
        args = SimpleNamespace(text=text, invert=False, export=export, out=None)
        cmd_qr(args)
        return True

    if name == "base64":
        mode = ask("encode or decode? (encode/decode)", "encode").lower()
        mode = "decode" if mode.startswith("d") else "encode"
        source = ask("text, or a file? (text/file)", "text").lower()
        text = file = None
        if source.startswith("f"):
            file = ask("file path (or drag & drop the file here)")
            while not file or not Path(file).expanduser().exists():
                file = ask("couldn't find that file — path")
            file = str(Path(file).expanduser())
        else:
            text = ask("text to encode" if mode == "encode" else "base64 to decode")
            while not text:
                text = ask("text to encode" if mode == "encode" else "base64 to decode")
        out = None
        if mode == "decode":
            out = ask("output filename, in case the decoded result isn't text (blank to skip)", "") or None
        copy = ask("copy result to clipboard? (y/n)", "n").lower().startswith("y")
        args = SimpleNamespace(mode=mode, text=text, file=file, out=out, copy=copy)
        cmd_base64(args)
        return True

    if name == "dice":
        spec_input = ask("dice notation (e.g. 2d6, d20, 4d6+2 — space-separated for multiple rolls)", "1d20")
        specs = spec_input.split() or ["1d20"]
        args = SimpleNamespace(specs=specs)
        cmd_dice(args)
        return True

    if name == "morse":
        mode = ask("encode or decode? (encode/decode)", "encode").lower()
        mode = "decode" if mode.startswith("d") else "encode"
        text = ask("text to encode" if mode == "encode" else "morse code to decode (use / between words)")
        while not text:
            text = ask("text to encode" if mode == "encode" else "morse code to decode (use / between words)")
        copy = ask("copy result to clipboard? (y/n)", "n").lower().startswith("y")
        args = SimpleNamespace(mode=mode, text=text, copy=copy)
        cmd_morse(args)
        return True

    if name == "sysinfo":
        cmd_sysinfo()
        return True

    # image/audio based tools: ascii-style file picker, then sensible defaults
    exts = AUDIO_EXTS if name == "waveform" else IMAGE_EXTS
    path = preset_path if preset_path and Path(preset_path).suffix.lower() in exts else None
    if not path:
        path = pick_file_gui(exts, f"select a file for {name}")
    if not path:
        path = ask("file path (or drag & drop the file here)")
    while not path or not Path(path).expanduser().exists():
        path = ask("couldn't find that file — path")
    path = str(Path(path).expanduser())
    print()

    if name == "palette":
        n = int(ask("how many colors", "6"))
        args = SimpleNamespace(image=path, colors=n, no_color=False, sort="freq", export=None, out=None)
        cmd_palette(args)
    elif name == "waveform":
        full = ask("full mirrored waveform, or a single compact line? (full/line)", "line").startswith("f")
        args = SimpleNamespace(
            audio=path, width="auto", height=16, full=full, color="00ffff", no_color=False,
            channel="mix", export=None, out=None,
        )
        cmd_waveform(args)

    return True


# ══════════════════════════════════════════════════════════════════════════
# entrypoint — no flags, no subcommands. just the menu.
# ══════════════════════════════════════════════════════════════════════════

def main():
    enable_ansi_on_windows()

    # convenience only, not a flag: drag a single file onto the script (or
    # pass its path as the one argument) and the menu opens with it preloaded.
    preset_path = None
    if len(sys.argv) == 2 and Path(sys.argv[1]).expanduser().exists():
        preset_path = str(Path(sys.argv[1]).expanduser())
    elif len(sys.argv) > 1:
        sys.exit("random ass tools takes no flags — just run `python tool.py` and pick from the menu.")

    # keep coming back to the menu until the user picks "exit"
    first_run = True
    while True:
        keep_going = interactive_menu(preset_path if first_run else None)
        first_run = False
        if not keep_going:
            break
        print()


if __name__ == "__main__":
    main()