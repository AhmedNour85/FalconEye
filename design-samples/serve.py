"""Serve the layout samples for viewing: only design-samples/ and frontend/ (for the Operation page's own styles), on this computer only.
Never the project root, so .env and the backend are not reachable.   python design-samples/serve.py   ->   http://127.0.0.1:8030/design-samples/"""
import functools
import http.server
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWED = ("/design-samples/", "/frontend/")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/design-samples"):
            self.send_response(302); self.send_header("Location", "/design-samples/"); self.end_headers(); return
        if ".." in path or not path.startswith(ALLOWED):
            self.send_error(404); return
        super().do_GET()

    do_HEAD = do_GET


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", 8030), functools.partial(Handler, directory=str(ROOT))).serve_forever()
