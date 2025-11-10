import os

from asgiref.wsgi import WsgiToAsgi

from src import create_app

app = create_app()
asgi_app = WsgiToAsgi(app)


def _debug_enabled() -> bool:
    debug_flag = os.environ.get("FLASK_DEBUG")
    if debug_flag is None:
        return True
    return debug_flag.lower() in {"1", "true", "on", "yes"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    try:
        app.run(host="0.0.0.0", port=port, debug=_debug_enabled())
    except OSError as exc:
        message = (
            f"Failed to bind to port {port}: {exc}. "
            "Try a different PORT value or ensure the current port is permitted and free."
        )
        raise SystemExit(message) from exc
