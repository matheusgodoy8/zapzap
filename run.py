"""Convenient checkout launcher for local and Flatpak development."""

import sys


def local(args):
    """Run the installed editable checkout with optional application args."""
    print("# === Running locally ===")
    sys.argv = [sys.argv[0], *args]

    from zapzap.app.application import main as application_main

    return application_main()


def flatpak(args):
    """Build and run the checkout in Flatpak mode."""
    from tools.flatpak_runner import FlatpakRunner

    return FlatpakRunner(args).run()


def main():
    """Run locally by default; reserve Flatpak setup for ``--flatpak``."""
    args = sys.argv[1:]
    selected_method = local

    if "--flatpak" in args:
        args.remove("--flatpak")
        selected_method = flatpak

    return selected_method(args)


if __name__ == "__main__":
    sys.exit(main())
