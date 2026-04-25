"""
Windows screen capture for the Blender window.
Returns a base64-encoded JPEG string for live streaming via SSE.

Optional dependencies — if not installed the functions return None gracefully:
  pip install mss Pillow pywin32
"""
import base64
import io

try:
    import mss
    from PIL import Image
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


def get_blender_window_rect() -> tuple[int, int, int, int] | None:
    """
    Return (left, top, right, bottom) of the first visible Blender window,
    or None if win32gui is unavailable or no window found.
    """
    if not WIN32_AVAILABLE:
        return None

    result: list[tuple[int, int, int, int]] = []

    def _cb(hwnd, _extra):
        title = win32gui.GetWindowText(hwnd)
        if "Blender" in title and win32gui.IsWindowVisible(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            # Skip tiny/minimised windows
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w > 100 and h > 100:
                result.append(rect)

    win32gui.EnumWindows(_cb, None)
    return result[0] if result else None


def capture_blender_frame(max_width: int = 960, jpeg_quality: int = 70) -> str | None:
    """
    Capture the Blender window and return a base64-encoded JPEG string.
    Returns None if mss / win32gui are unavailable or Blender is not open.
    """
    if not MSS_AVAILABLE:
        return None

    rect = get_blender_window_rect()
    if rect is None:
        return None

    l, t, r, b = rect
    width = r - l
    height = b - t
    if width <= 0 or height <= 0:
        return None

    try:
        with mss.mss() as sct:
            monitor = {"left": l, "top": t, "width": width, "height": height}
            shot = sct.grab(monitor)
            # mss gives BGRA — convert to RGB via Pillow
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        # Down-scale to max_width while preserving aspect ratio
        aspect = height / width
        new_w = min(max_width, width)
        new_h = int(new_w * aspect)
        if new_w != width:
            img = img.resize((new_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    except Exception:
        return None


def capture_blender_frame_safe() -> str | None:
    """Wrapper that swallows all exceptions — safe to call from any context."""
    try:
        return capture_blender_frame()
    except Exception:
        return None
