"""A tiny local web server that imitates the two practice sites, so tests need no internet."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = self.server.routes.get(self.path, (404, "not found"))
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html")      # no charset on purpose, like the real site
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):                           # keep test output quiet
        pass


@pytest.fixture
def serve():
    """serve(routes) -> base URL. routes = {path: (status, html)}."""
    servers = []

    def _serve(routes):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.routes = routes
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}/"

    yield _serve
    for s in servers:
        s.shutdown()
        s.server_close()


# ---------- HTML builders ----------
def book_html(title, href, price="£10.00", rating="Three"):
    price_html = f'<div class="product_price"><p class="price_color">{price}</p></div>' if price else ""
    return (f'<article class="product_pod"><p class="star-rating {rating}"></p>'
            f'<h3><a href="{href}" title="{title}">{title[:10]}...</a></h3>{price_html}</article>')


def listing(articles, next_href=None):
    nxt = f'<ul class="pager"><li class="next"><a href="{next_href}">next</a></li></ul>' if next_href else ""
    return f"<html><body>{''.join(articles)}{nxt}</body></html>"


def detail(category, description):
    return ('<html><body><ul class="breadcrumb"><li><a href="/">Home</a></li><li><a href="#">Books</a></li>'
            f'<li><a href="#">{category}</a></li><li class="active">x</li></ul>'
            f'<div id="product_description" class="sub-header"><h2>Product Description</h2></div>'
            f'<p>{description}</p></body></html>')


def quote_html(text, author, tags=()):
    tag_html = "".join(f'<a class="tag" href="/tag/{t}/">{t}</a>' for t in tags)
    return (f'<div class="quote"><span class="text">\u201c{text}\u201d</span>'
            f'<span>by <small class="author">{author}</small><a href="/author/x">(about)</a></span>'
            f'<div class="tags">Tags: {tag_html}</div></div>')


def books_site():
    return {
        "/": (200, listing([
            book_html("Book One", "catalogue/book-one_1/index.html", "£51.77", "Three"),
            book_html("Book Two", "catalogue/book-two_2/index.html", "£20.00", "Five"),
        ], "catalogue/page-2.html")),
        "/catalogue/page-2.html": (200, listing([
            book_html("Book Three", "book-three_3/index.html", "£10.00", "One"),
            book_html("  BOOK  three ", "book-three-again_4/index.html", "£10.00", "One"),   # duplicate
            book_html("No Price Book", "no-price_5/index.html", price=None),                  # rejected
        ])),
        "/catalogue/book-one_1/index.html": (200, detail("Poetry", "A  fine\n book.")),
        "/catalogue/book-three_3/index.html": (200, detail("Fiction", "Third.")),
        # book-two, the duplicate and no-price have NO detail page -> 404 -> detail failure
    }


def quotes_site(page2_status=200, page1_status=200):
    return {
        "/": (page1_status, listing([
            quote_html("The world is a book.", "Saint Augustine", ["Travel", "books"]),
            quote_html("No tags here\xa0 at all", "Anon"),
        ], "/page/2/")),
        "/page/2/": (page2_status, listing([quote_html("Third quote", "Jane Austen", ["life"])])),
    }
