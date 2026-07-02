"""
ascii — turn any image into ASCII art.

Run with no arguments for an interactive menu (with a GUI file picker if
available). Run with a path and flags for the fast, scriptable path.

Works with any image format Pillow can open (PNG, JPG, WEBP, BMP, GIF, TIFF,
etc). If the image has a transparent background (PNG/WEBP/GIF/TIFF with real
alpha), transparent pixels are skipped so the ASCII output keeps the
subject's silhouette instead of filling in a rectangle.

Usage:
    python ascii.py                              interactive menu + file picker
    python ascii.py image.png                    quick render, defaults
    python ascii.py image.png --width 120
    python ascii.py image.png --charset blocks --no-color
    python ascii.py image.png --export png --out result.png
    python ascii.py image.png --copy
    python ascii.py dance.gif --animate
    python ascii.py *.png --export txt
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageSequence, UnidentifiedImageError

CHARSETS = {
    "default": " .:-=+*#%@",
    "blocks": " ░▒▓█",
    "binary": " #",
    "detailed": " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
}

RESET = "\033[0m"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif"}


def enable_ansi_on_windows():
    """Turn on ANSI/VT100 escape processing in classic cmd.exe (no-op elsewhere).

    Windows Terminal, PowerShell 7+, and modern terminals already support
    truecolor ANSI codes, but legacy cmd.exe consoles need this switched on
    explicitly before colored output or --animate's screen-clear codes work.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass


def find_monospace_font() -> str | None:
    """Locate a decent monospace TTF/TTC for PNG export, per platform. Returns None if none found."""
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates += [
            "/System/Library/Fonts/Menlo.ttc",
            "/System/Library/Fonts/Monaco.ttf",
            "/System/Library/Fonts/SFNSMono.ttf",
            "/Library/Fonts/Courier New.ttf",
        ]
    elif sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        candidates += [
            str(Path(windir) / "Fonts" / "consola.ttf"),
            str(Path(windir) / "Fonts" / "cour.ttf"),
            str(Path(windir) / "Fonts" / "lucon.ttf"),
        ]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/local/share/fonts/DejaVuSansMono.ttf",
        ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None

SIZE_PRESETS = {
    "1": ("small", "60"),
    "2": ("medium", "100"),
    "3": ("large", "160"),
    "4": ("huge", "220"),
    "5": ("auto (fit terminal)", "auto"),
}


# ── loading ──────────────────────────────────────────────────────────────

def load_image(path: str) -> tuple[Image.Image, bool]:
    """Load any Pillow-supported image. Returns (image, has_transparency)."""
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
    alpha_min, _alpha_max = rgba.getchannel("A").getextrema()
    has_transparency = alpha_min < 255

    return rgba, has_transparency


def load_animation_frames(path: str):
    """Return a list of (RGBA frame, duration_ms), or None if not multi-frame."""
    img = Image.open(path)
    n_frames = getattr(img, "n_frames", 1)
    if n_frames <= 1:
        return None

    frames = []
    for frame in ImageSequence.Iterator(img):
        duration = frame.info.get("duration", 100)
        frames.append((frame.convert("RGBA"), duration))
    return frames


# ── image processing ────────────────────────────────────────────────────

def resize_image(img: Image.Image, new_width: int, char_aspect: float = 0.55) -> Image.Image:
    """Resize keeping aspect ratio, compensating for terminal characters being taller than wide."""
    w, h = img.size
    ratio = h / w
    new_height = max(1, int(new_width * ratio * char_aspect))
    return img.resize((new_width, new_height), Image.LANCZOS)


def brightness(r: int, g: int, b: int) -> float:
    """Perceptual luminance."""
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def char_for_brightness(value: float, charset: str, invert: bool) -> str:
    chars = charset[::-1] if invert else charset
    idx = int((value / 255) * (len(chars) - 1))
    return chars[idx]


def parse_hex_color(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        sys.exit(f"error: '--tint {s}' isn't a valid hex color, expected format like ff8800")
    try:
        return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        sys.exit(f"error: '--tint {s}' isn't a valid hex color, expected format like ff8800")


def build_ascii_grid(
    img: Image.Image,
    charset_name: str,
    invert: bool,
    alpha_threshold: int,
    block_char: str | None,
    tint: tuple[int, int, int] | None = None,
):
    """Return a 2D grid of (char, (r,g,b) or None) — None means transparent/blank."""
    charset = CHARSETS[charset_name]
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
            val = brightness(r, g, b)
            ch = block_char if block_char else char_for_brightness(val, charset, invert)
            if tint:
                scale = val / 255
                r, g, b = (int(c * scale) for c in tint)
            row.append((ch, (r, g, b)))
        grid.append(row)
    return grid


# ── rendering ────────────────────────────────────────────────────────────

def render_terminal(grid, color: bool) -> str:
    lines = []
    for row in grid:
        line_parts = []
        for ch, rgb in row:
            if rgb is None or not color:
                line_parts.append(ch)
            else:
                r, g, b = rgb
                line_parts.append(f"\033[38;2;{r};{g};{b}m{ch}{RESET}")
        lines.append("".join(line_parts))
    return "\n".join(lines)


def render_plain(grid) -> str:
    """Plain text version (no ANSI codes), used for --export txt and --copy."""
    return "\n".join("".join(ch for ch, _ in row) for row in grid)


def export_png(grid, out_path: str, font_size: int = 12, bg=(0, 0, 0, 0)):
    """Render the ASCII grid onto a PNG, colored per character."""
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


def export_html(grid, out_path: str, font_size: int = 14, bg: str = "#0d1117"):
    """Render the ASCII grid as a standalone, shareable HTML page."""
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
<html>
<head>
<meta charset="utf-8">
<title>ASCII Art</title>
<style>
  body {{ background:{bg}; margin:0; padding:24px; }}
  .ascii {{
    font-family: 'Consolas', 'Menlo', 'DejaVu Sans Mono', 'Courier New', monospace;
    font-size: {font_size}px;
    line-height: 1;
    white-space: pre;
  }}
</style>
</head>
<body>
<div class="ascii">{body}</div>
</body>
</html>"""
    Path(out_path).write_text(html, encoding="utf-8")


# ── clipboard ────────────────────────────────────────────────────────────

def copy_to_clipboard(text: str) -> bool:
    """Try several clipboard mechanisms depending on platform. Returns success."""
    try:
        import pyperclip  # optional dependency, used first if available

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


# ── animation ────────────────────────────────────────────────────────────

def play_animation(frames, width, charset_name, invert, alpha_threshold, block_char, color, fps, loops, tint):
    fixed_interval = (1 / fps) if fps else None
    played = 0
    try:
        while loops == 0 or played < loops:
            for frame_img, duration_ms in frames:
                resized = resize_image(frame_img, width)
                grid = build_ascii_grid(resized, charset_name, invert, alpha_threshold, block_char, tint)
                sys.stdout.write("\033[H\033[J")
                sys.stdout.write(render_terminal(grid, color))
                sys.stdout.flush()
                time.sleep(fixed_interval if fixed_interval else max(duration_ms, 20) / 1000)
            played += 1
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)


# ── stats ────────────────────────────────────────────────────────────────

def print_stats(path, img, has_transparency, grid):
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    print(
        f"stats: {path}\n"
        f"  source size     {img.size[0]}x{img.size[1]}px\n"
        f"  output size     {cols}x{rows} chars\n"
        f"  transparency    {'yes' if has_transparency else 'no'}",
        file=sys.stderr,
    )


# ── file picker (for interactive mode) ──────────────────────────────────

def list_images(base_dirs):
    files = []
    for d in base_dirs:
        p = Path(d).expanduser()
        if not p.exists():
            continue
        try:
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                    files.append(f)
        except PermissionError:
            continue
    return files


def pick_file_gui():
    """Try the best native file picker for the current OS, then fall back to a
    cross-platform Tk dialog. Returns a path, or None if nothing is available
    or the user cancels."""

    if sys.platform == "darwin":
        script = 'POSIX path of (choose file with prompt "select an image")'
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=120
            )
            out = result.stdout.strip()
            if result.returncode == 0 and out:
                return out
            return None  # user cancelled
        except Exception:
            pass  # fall through to Tk below

    elif not sys.platform.startswith("win"):
        # Linux: native dialogs first, then a dmenu-style list via wofi/rofi
        for tool, args in (
            ("zenity", ["--file-selection", "--title=select an image"]),
            ("yad", ["--file-selection", "--title=select an image"]),
        ):
            if shutil.which(tool):
                try:
                    result = subprocess.run([tool, *args], capture_output=True, text=True, timeout=120)
                    out = result.stdout.strip()
                    if result.returncode == 0 and out:
                        return out
                    return None  # user cancelled the dialog
                except Exception:
                    continue

        for tool, args in (
            ("wofi", ["--dmenu", "--prompt", "select image"]),
            ("rofi", ["-dmenu", "-p", "select image"]),
        ):
            if shutil.which(tool):
                candidates = list_images([Path.home() / "Pictures", Path.home() / "Downloads", Path.cwd()])
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

    # Cross-platform fallback (this is the primary picker on Windows, and a
    # backup everywhere else): Tk's built-in file dialog. Ships with the
    # standard python.org / Microsoft Store installers on Windows and macOS;
    # on Linux it may need a `python3-tk` package.
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="select an image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff *.tif"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        return path or None
    except Exception:
        return None


# ── interactive menu ────────────────────────────────────────────────────

def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def interactive_menu():
    print("\n\033[1masciiart — interactive mode\033[0m\n")

    print("opening file picker...")
    path = pick_file_gui()

    if not path:
        path = ask("image path (or drag & drop the file here)")
    while not path or not Path(path).expanduser().exists():
        path = ask("couldn't find that file — image path")
    path = str(Path(path).expanduser())

    print("\nsize:")
    for key, (label, _) in SIZE_PRESETS.items():
        print(f"  {key}) {label}")
    size_choice = ask("choose a size", "2")
    if size_choice in SIZE_PRESETS:
        width = SIZE_PRESETS[size_choice][1]
    elif size_choice.isdigit():
        width = size_choice
    else:
        width = "100"

    print("\ncharset:")
    keys = list(CHARSETS.keys())
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

    export = None
    out = None
    if not animate:
        export_choice = ask("export to a file? (n/txt/png/html)", "n").lower()
        if export_choice in ("txt", "png", "html"):
            export = export_choice
            out = ask("output filename", f"{Path(path).stem}_ascii.{export}")

    copy = False
    if not animate:
        copy = ask("copy to clipboard? (y/n)", "n").lower().startswith("y")

    print()
    args = argparse.Namespace(
        width=width,
        charset=charset,
        block=block,
        invert=False,
        no_color=not color,
        tint=tint,
        alpha_threshold=10,
        export=export,
        out=out,
        font_size=12,
        copy=copy,
        stats=False,
        animate=animate,
        fps=0,
        loops=1,
    )

    if animate:
        frames = load_animation_frames(path)
        if frames is None:
            print("note: that image isn't actually animated, rendering a single frame instead.\n", file=sys.stderr)
            process_image(path, args)
        else:
            w = resolve_width(args.width)
            block_char = "█" if args.block else None
            tint_rgb = parse_hex_color(args.tint) if args.tint else None
            print("playing — press Ctrl+C to stop\n")
            play_animation(frames, w, args.charset, args.invert, args.alpha_threshold, block_char, color, args.fps, args.loops, tint_rgb)
    else:
        process_image(path, args)


# ── single image pipeline ───────────────────────────────────────────────

def process_image(path, args):
    img, has_transparency = load_image(path)
    if not has_transparency:
        print(
            f"note: no transparency detected in '{path}', rendering the full frame.",
            file=sys.stderr,
        )

    width = resolve_width(args.width)
    resized = resize_image(img, width)

    block_char = "█" if args.block else None
    tint = parse_hex_color(args.tint) if args.tint else None

    grid = build_ascii_grid(
        resized,
        charset_name=args.charset,
        invert=args.invert,
        alpha_threshold=args.alpha_threshold,
        block_char=block_char,
        tint=tint,
    )

    print(render_terminal(grid, color=not args.no_color))

    if args.stats:
        print_stats(path, img, has_transparency, grid)

    if args.export:
        stem = Path(path).stem
        out_path = args.out or f"{stem}_ascii.{args.export}"
        if args.export == "txt":
            Path(out_path).write_text(render_plain(grid), encoding="utf-8")
        elif args.export == "html":
            export_html(grid, out_path, font_size=args.font_size)
        else:
            export_png(grid, out_path, font_size=args.font_size)
        print(f"saved to {out_path}", file=sys.stderr)

    if args.copy:
        ok = copy_to_clipboard(render_plain(grid))
        if ok:
            print("copied to clipboard", file=sys.stderr)
        else:
            print(
                "warning: couldn't find a clipboard tool.\n"
                "         install one of: xclip, xsel, wl-copy, or `pip install pyperclip`.",
                file=sys.stderr,
            )


def resolve_width(width_arg: str) -> int:
    if width_arg == "auto":
        return max(20, shutil.get_terminal_size((100, 24)).columns)
    try:
        return int(width_arg)
    except ValueError:
        sys.exit(f"error: --width must be a number or 'auto', got '{width_arg}'")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    enable_ansi_on_windows()
    parser = argparse.ArgumentParser(description="Convert an image into ASCII art.")
    parser.add_argument(
        "images", nargs="*", help="path(s) to image(s) — PNG, JPG, WEBP, BMP, GIF, TIFF, etc. Omit for interactive mode."
    )
    parser.add_argument("--menu", action="store_true", help="force interactive menu even if an image is given")
    parser.add_argument(
        "--width", default="100", help="output width in characters, or 'auto' to fit your terminal (default: 100)"
    )
    parser.add_argument(
        "--charset",
        choices=CHARSETS.keys(),
        default="default",
        help="character set used for brightness mapping (default: default)",
    )
    parser.add_argument("--block", action="store_true", help="use solid blocks (█) instead of a gradient charset")
    parser.add_argument("--invert", action="store_true", help="invert brightness mapping (for light backgrounds)")
    parser.add_argument("--no-color", action="store_true", help="disable colored output, grayscale characters only")
    parser.add_argument("--tint", metavar="HEX", help="recolor the art with a single tint color, e.g. --tint 00ffff")
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=10,
        help="alpha value below which a pixel is treated as transparent (0-255, default: 10)",
    )
    parser.add_argument("--export", choices=["txt", "png", "html"], help="also export the result to a file")
    parser.add_argument("--out", help="output file path for --export (default: <image_name>_ascii.<ext>)")
    parser.add_argument("--font-size", type=int, default=12, help="font size for PNG/HTML export (default: 12)")
    parser.add_argument("--copy", action="store_true", help="copy the plain ASCII art to your clipboard")
    parser.add_argument("--stats", action="store_true", help="print quick info about the image and output")
    parser.add_argument("--animate", action="store_true", help="play an animated GIF/WEBP frame-by-frame in the terminal")
    parser.add_argument("--fps", type=float, default=0, help="fixed playback speed for --animate (default: use each frame's native timing)")
    parser.add_argument("--loops", type=int, default=1, help="how many times to loop --animate (0 = forever, default: 1)")

    args = parser.parse_args()

    if not args.images or args.menu:
        interactive_menu()
        return

    if args.animate:
        if len(args.images) > 1:
            sys.exit("error: --animate only supports one image at a time.")
        frames = load_animation_frames(args.images[0])
        if frames is None:
            sys.exit(f"error: '{args.images[0]}' isn't an animated image (no multiple frames found).")
        width = resolve_width(args.width)
        block_char = "█" if args.block else None
        tint = parse_hex_color(args.tint) if args.tint else None
        play_animation(
            frames, width, args.charset, args.invert, args.alpha_threshold,
            block_char, not args.no_color, args.fps, args.loops, tint,
        )
        return

    if args.copy and len(args.images) > 1:
        sys.exit("error: --copy only supports one image at a time.")

    for path in args.images:
        if len(args.images) > 1:
            print(f"\n=== {path} ===", file=sys.stderr)
        process_image(path, args)


if __name__ == "__main__":
    main()