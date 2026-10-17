"""X11 backdrop for testing EV's island on Linux (Hyprland + XWayland).

Under XWayland, EV only learns the pointer position while the pointer is over
an X11 window. This plain window gives the island an X11 surface to hang over.
Usage: python3 backdrop.py [css-color]   (run with GDK_BACKEND=x11)
"""

import sys

import gi
from gi.repository import GLib

# Window class for compositor rules; must be set before GTK starts.
GLib.set_prgname("ev-backdrop")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

color = sys.argv[1] if len(sys.argv) > 1 else "#ffffff"
window = Gtk.Window(title="ev-backdrop")
window.set_default_size(800, 400)
css = Gtk.CssProvider()
css.load_from_data(f"window {{ background: {color}; }}".encode())
Gtk.StyleContext.add_provider_for_screen(
    Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
)
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
