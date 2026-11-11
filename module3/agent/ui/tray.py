import threading
from PIL import Image, ImageDraw

try:
    import pystray
except ImportError:
    pystray = None

TRANSPARENCY_NOTE = (
    "Cyber XAI Endpoint Agent (Active)\n"
    "This tool records USB use, copy volumes and whether sensitive-looking text is copied.\n"
    "It does not record file names or content."
)

def _create_shield_icon():
    img = Image.new("RGB", (64, 64), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.polygon([(32, 8), (54, 18), (48, 46), (32, 56), (16, 46), (10, 18)], fill=(16, 185, 129), outline=(255, 255, 255))
    return img

class AgentTrayUI:
    def __init__(self, stop_event: threading.Event, status_callback=None):
        self.stop_event = stop_event
        self.status_callback = status_callback
        self.icon = None

    def _on_quit(self, icon, item):
        self.stop_event.set()
        if icon:
            icon.stop()

    def start_in_background(self):
        if pystray is None:
            return None
        menu = pystray.Menu(
            pystray.MenuItem("Cyber XAI Agent: Running", lambda: None, enabled=False),
            pystray.MenuItem("Privacy: Metadata Only (No Filenames/Content)", lambda: None, enabled=False),
            pystray.MenuItem("Stop Agent", self._on_quit)
        )
        self.icon = pystray.Icon("cyber_xai_agent", _create_shield_icon(), TRANSPARENCY_NOTE, menu)
        t = threading.Thread(target=self.icon.run, name="tray_ui", daemon=True)
        t.start()
        return t
