from __future__ import annotations

import asyncio
import configparser
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import feedparser
import httpx
import pytz
from jinja2 import Environment, FileSystemLoader

FeedEntry = tuple[str, str, str, tuple[int, ...] | None, str]


def find_config_file() -> Path:
    """Find the configuration file in the same directory as this script."""
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / "config.ini"
    if not config_path.is_file():
        msg = f"Config file not found at {config_path}"
        raise FileNotFoundError(msg)
    return config_path


def read_config() -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """Read the configuration file and return a list of feed URLs and names, and Planet-wide settings."""
    config_path = find_config_file()
    config = configparser.ConfigParser(interpolation=None)
    config.read(config_path)

    feeds = []
    for section in config.sections():
        if section != "Planet":
            url = section
            name = config[section].get("name", url)
            feeds.append((url, name))

    planet_config = {
        "date_format": config["Planet"].get("date_format", "%B %d, %Y %I:%M %p %Z"),
        "name": config["Planet"].get("name", "Planet Python"),
        "encoding": config["Planet"].get("encoding", "utf-8"),
        "items_per_page": config["Planet"].getint("items_per_page", 25),
        "max_pages": config["Planet"].getint("max_pages", 10),  # Default to 10 pages
        "output_dir": Path(config["Planet"].get("output_dir", "./output")),
        "new_date_format": config["Planet"].get("new_date_format", "%B %d, %Y"),
        "activity_threshold": config["Planet"].getint("activity_threshold", 180),
    }

    print(f"Found {len(feeds)} feeds in the configuration file.")
    return feeds, planet_config


def parse_feed_content(content: str, name: str, url: str) -> list[tuple[Any, Any, Any, Any, str, str]]:
    """Parse feed content and return a list of entries."""
    feed = feedparser.parse(content)
    entries = [
        (
            entry.title,
            entry.link,
            entry.summary,
            entry.get("published_parsed") or entry.get("updated_parsed"),
            name,
            url,
        )
        for entry in feed.entries
    ]
    print(f"Found {len(entries)} entries for feed: {name}")
    return entries


async def get_feed_content(client: httpx.AsyncClient, url: str) -> str:
    """Fetch feed content from the given URL."""
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.text


async def parse_feed(
    client: httpx.AsyncClient, url: str, name: str
) -> tuple[list[Any], bool] | tuple[list[tuple[Any, Any, Any, Any, str, str]], bool]:
    """Parse a feed and return a list of entries and a flag indicating if it's a 404."""
    content: str | None = None
    is_404 = False

    try:
        content = await get_feed_content(client, url)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:  # noqa: PLR2004
            print(f"404 error parsing feed {name}: {e}")
            is_404 = True
        else:
            print(f"HTTP error parsing feed {name}: {e}")
    except ssl.SSLCertVerificationError:
        print(f"SSL certificate verification failed for feed {name}. Attempting without verification...")
        try:
            async with httpx.AsyncClient(verify=False) as insecure_client:  # noqa: S501
                content = await get_feed_content(insecure_client, url)
        except Exception as e:  # noqa: BLE001
            print(f"Error parsing feed {name} without SSL verification: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"Error parsing feed {name}: {e}")

    if not content:
        return [], is_404
    entries = parse_feed_content(content, name, url)
    return entries, False


def generate_pagination(page: int, total_pages: int) -> str:
    """Generate pagination HTML."""
    pagination = '<div class="btn-group my-4">'
    if page > 1:
        pagination += f'<a href="index{page-1}.html" class="btn">«</a>'
    for i in range(max(1, page - 2), min(total_pages + 1, page + 3)):
        if i == page:
            pagination += (
                f'<button class="btn btn-active hover:bg-primary hover:shadow-lg hover:shadow-primary/50">{i}</button>'
            )
        else:
            pagination += (
                f'<a href="index{i}.html" class="btn hover:bg-primary hover:shadow-lg hover:shadow-primary/50">{i}</a>'
            )
    if page < total_pages:
        pagination += f'<a href="index{page+1}.html" class="btn">»</a>'
    pagination += "</div>"
    return pagination


def generate_feed_list(feeds: list[tuple[str, str]]) -> str:
    """Generate feed list HTML."""
    return "".join(f'<li><a href="{url}">{name}</a></li>' for url, name in feeds)


def generate_top_authors(entries: list[FeedEntry]) -> str:
    """Generate top authors HTML."""
    authors = {}
    for _, _, _, _, feed_name, feed_url in entries:
        authors[feed_name] = authors.get(feed_name, 0) + 1
    top_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5]
    return "".join(
        f'<li><a href="{feed_url}">{name} ({count})</a></li>'
        for (name, count), feed_url in zip(
            top_authors, [e[5] for e in entries if e[4] in [a[0] for a in top_authors]], strict=False
        )
    )


def generate_stats(entries: list[FeedEntry]) -> str:
    """Generate stats HTML."""
    total_entries = len(entries)
    unique_feeds = len({entry[4] for entry in entries})
    return f"""
    <li><a>Total Entries: {total_entries}</a></li>
    <li><a>Unique Feeds: {unique_feeds}</a></li>
    """


def render_template(template_name: str, context: dict) -> str:
    """Render a Jinja2 template with the given context."""
    template_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
    template = env.get_template(template_name)
    return template.render(context)


def generate_html_content(  # noqa: PLR0913
    entries: list[FeedEntry],
    page: int,
    total_pages: int,
    feeds: list[tuple[str, str]],
    all_entries: list[FeedEntry],
    planet_config: dict[str, Any],
) -> str:
    """Generate HTML content using Jinja2 templates."""
    pagination = generate_pagination(page, total_pages)

    context = {
        "entries": [
            {
                "title": title or "Unknown title",
                "link": link,
                "summary": summary,
                "date_str": (
                    datetime(*date[:6], tzinfo=pytz.utc).strftime(planet_config["date_format"])
                    if date
                    else "Unknown date"
                ),
                "feed_name": feed_name,
                "feed_url": feed_url,
            }
            for title, link, summary, date, feed_name, feed_url in entries
        ],
        "page": page,
        "total_pages": total_pages,
        "feeds": [{"name": name, "url": url} for url, name in feeds],
        "pagination": pagination,
        "top_authors": generate_top_authors(all_entries),
        "stats": generate_stats(all_entries),
        "planet_name": planet_config["name"],
        "encoding": planet_config["encoding"],
        "output_dir": planet_config["output_dir"].name,
    }

    return render_template("content.html", context)


async def write_html_file(output_dir: Path, filename: str, content: str) -> None:
    """Write HTML content to a file."""
    output_file = output_dir / filename
    async with aiofiles.open(output_file, mode="w", encoding="utf-8") as f:
        await f.write(content)
    print(f"Generated {filename}")


async def main() -> None:
    """Handle calls to generate the feed."""
    feeds, planet_config = read_config()
    output_dir = Path(planet_config["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        tasks = [parse_feed(client, url, name) for url, name in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_entries: list[FeedEntry] = []
    feeds_to_prune: list[str] = []

    for (url, name), result in zip(feeds, results, strict=False):
        if isinstance(result, tuple):
            entries, is_404 = result
            all_entries.extend(entries)
            if is_404:
                feeds_to_prune.append(url)  # TODO: Missing some feeds somehow...
        else:
            print(f"Error occurred for feed {name}: {result}")

    all_entries.sort(key=lambda x: x[3] or (0,), reverse=True)
    entries_per_page = planet_config["items_per_page"]
    total_pages = min((len(all_entries) + entries_per_page - 1) // entries_per_page, planet_config["max_pages"])

    for page in range(1, total_pages + 1):
        start_index = (page - 1) * entries_per_page
        end_index = start_index + entries_per_page
        page_entries = all_entries[start_index:end_index]

        html_content = generate_html_content(page_entries, page, total_pages, feeds, all_entries, planet_config)

        filename = "index1.html" if page == 1 else f"index{page}.html"  # Correct filenames
        await write_html_file(output_dir, filename, html_content)

    print(f"Successfully generated {total_pages} pages with {len(all_entries)} total entries")

    if feeds_to_prune:
        prune_file = output_dir / "feeds_to_prune.txt"
        async with aiofiles.open(prune_file, mode="w", encoding="utf-8") as f:
            await f.write("\n".join(feeds_to_prune))
        print(f"Generated list of feeds to prune at {prune_file}")


if __name__ == "__main__":
    asyncio.run(main())
