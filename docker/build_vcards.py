from __future__ import annotations

import html
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path


IGNORED_DIRS = {
    ".agents",
    ".codex",
    ".git",
    "docker",
    "node_modules",
}

IGNORED_FILES = {
    ".dockerignore",
    "docker-compose.yml",
    "Dockerfile",
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or "vcard"


def should_skip(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True

    return any(part in IGNORED_DIRS for part in relative.parts)


def discover_sites(root: Path) -> list[dict[str, str | Path]]:
    sites = []

    for index_path in sorted(root.rglob("index.html")):
        if should_skip(index_path, root):
            continue

        site_dir = index_path.parent
        if site_dir == root:
            continue

        display_name = site_dir.parent.name if site_dir.parent != root else site_dir.name
        slug = slugify(display_name)
        original_slug = slug
        counter = 2

        existing_slugs = {site["slug"] for site in sites}
        while slug in existing_slugs:
            slug = f"{original_slug}-{counter}"
            counter += 1

        sites.append(
            {
                "display_name": display_name,
                "slug": slug,
                "source": site_dir,
            }
        )

    return sorted(sites, key=lambda site: str(site["display_name"]).casefold())


def copy_site(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if item.name in IGNORED_FILES:
            continue

        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def build_index(sites: list[dict[str, str | Path]]) -> str:
    items = "\n".join(
        f'        <li><a href="/{site["slug"]}/">{html.escape(str(site["display_name"]))}</a></li>'
        for site in sites
    )

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCARDs</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f7f4;
      color: #202124;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
    }}

    main {{
      width: min(980px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0;
    }}

    h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 5vw, 3.5rem);
      line-height: 1;
      letter-spacing: 0;
    }}

    p {{
      margin: 0 0 28px;
      max-width: 680px;
      color: #62645f;
      font-size: 1rem;
      line-height: 1.6;
    }}

    ul {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}

    a {{
      display: block;
      min-height: 54px;
      padding: 16px 18px;
      border: 1px solid #deded8;
      border-radius: 8px;
      background: #ffffff;
      color: #202124;
      text-decoration: none;
      font-weight: 650;
      line-height: 1.25;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}

    a:hover,
    a:focus-visible {{
      border-color: #2f6f62;
      outline: none;
    }}
  </style>
</head>
<body>
  <main>
    <h1>VCARDs</h1>
    <ul>
{items}
    </ul>
  </main>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: build_vcards.py <source-root> <output-root>", file=sys.stderr)
        return 2

    source_root = Path(sys.argv[1]).resolve()
    output_root = Path(sys.argv[2]).resolve()

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    sites = discover_sites(source_root)
    if not sites:
        print("No vCard sites with index.html were found.", file=sys.stderr)
        return 1

    for site in sites:
        copy_site(Path(site["source"]), output_root / str(site["slug"]))

    public_sites = [
        {
            "name": str(site["display_name"]),
            "path": f"/{site['slug']}/",
        }
        for site in sites
    ]

    (output_root / "index.html").write_text(build_index(sites), encoding="utf-8")
    (output_root / "routes.json").write_text(
        json.dumps(public_sites, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Built {len(sites)} vCard routes:")
    for site in sites:
        print(f"  /{site['slug']}/ <- {site['source']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
