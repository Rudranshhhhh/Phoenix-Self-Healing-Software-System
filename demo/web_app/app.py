"""Demo web app that stays running; GET /product fails with a KeyError."""
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO)

PRODUCTS = {"apple": {"cost": 10}}


def get_product(name):
    product = PRODUCTS[name]
    return product["price"]


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, text):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == "/health":
                self._reply(200, "ok")
            elif self.path == "/product":
                self._reply(200, str(get_product("apple")))
            else:
                self._reply(404, "not found")
        except Exception:
            logging.exception("request failed: %s", self.path)
            self._reply(500, "internal error")

    def log_message(self, fmt, *args):
        logging.info(fmt, *args)


if __name__ == "__main__":
    logging.info("web-app listening on 8080")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()