import argparse
import logging
import pathlib
import random
import shutil
import sys
from typing import Any, Dict, Optional, Tuple

import httpx

import dragnet_data

logging.basicConfig(level=logging.INFO)

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:75.0) Gecko/20100101 Firefox/75.0",
)


def main():
    parser = argparse.ArgumentParser(
        description="Script to fetch HTML documents and some metadata for a set of pages "
        "published to a curated collection of RSS feeds -- and, when possible, "
        "to extract a first pass on the page's main body text.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_arguments(parser)
    args = parser.parse_args()
    # fetch base data from rss feeds
    rss_pages = []
    feeds = dragnet_data.utils.load_json_data(args.feeds_fpath)
    for feed in feeds:
        entries = dragnet_data.rss.get_entries_from_feed(feed, maxn=args.maxn_entries_per_feed)
        rss_pages.extend(
            dragnet_data.rss.get_data_from_entry(entry) for entry in entries
        )
    # just in case: remove any rss pages without urls, since we need them next
    rss_pages = [rss_page for rss_page in rss_pages if rss_page.get("url")]
    logging.info("got data for %s pages from RSS feeds", len(rss_pages))
    dragnet_data.utils.save_json_data(
        rss_pages, args.data_dirpath.joinpath("rss_pages.json"),
    )
    # fetch html and re-extract base metadata, plus text if available
    rss_pages = random.sample(rss_pages, k=len(rss_pages))
    n_pages = len(rss_pages)
    with httpx.Client(timeout=args.http_timeout) as client:
        for idx, rss_page in enumerate(rss_pages):
            logging.info("getting data for page %s / %s", idx, n_pages)
            headers = {"user-agent": random.choice(USER_AGENTS)}
            result = get_page_html_and_data(
                rss_page["url"], client=client, headers=headers,
            )
            if result is None:
                continue
            else:
                html, data = result
                dragnet_data.utils.save_text_data(
                    html, args.data_dirpath.joinpath("html", f"{data['id']}.html"),
                )
                dragnet_data.utils.save_json_data(
                    data, args.data_dirpath.joinpath("meta", f"{data['id']}.json"),
                )
    # package file collections into archives
    shutil.make_archive(
        args.data_dirpath.joinpath("html", "html_files").resolve(),
        format="gztar",
        root_dir=args.data_dirpath.joinpath("html").resolve(),
    )
    shutil.make_archive(
        args.data_dirpath.joinpath("meta", "meta_files").resolve(),
        format="gztar",
        root_dir=args.data_dirpath.joinpath("meta").resolve(),
    )


def add_arguments(parser):
    parser.add_argument(
        "--feeds_fpath", type=pathlib.Path, default=pathlib.Path("./data/rss_feeds.json"),
    )
    parser.add_argument(
        "--data_dirpath", type=pathlib.Path, default=pathlib.Path("./data"),
    )
    parser.add_argument(
        "--maxn_entries_per_feed", type=int, default=25,
    )
    parser.add_argument(
        "--http_timeout", type=float, default=5.0,
    )


def get_page_html_and_data(
    url: str,
    client: Optional[httpx.Client] = None,
    **kwargs,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    try:
        html, response = dragnet_data.html.get_html(url, client=client, **kwargs)
    except httpx.HTTPError:
        logging.exception("unable to get HTML for %s", url)
        return
    try:
        data = dragnet_data.html.get_data_from_html(html)
    except Exception:
        logging.error("unable to extract data from HTML for %s", url)
        return
    if "url" not in data:
        data["url"] = str(response.url)
    data["id"] = dragnet_data.utils.generate_page_uuid(data["url"])
    return (html, data)


if __name__ == "__main__":
    sys.exit(main())
