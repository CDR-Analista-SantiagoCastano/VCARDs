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

TITLE_PATTERN = re.compile(r"<title>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or "vcard"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def read_display_name(index_path: Path, fallback: str) -> str:
    content = index_path.read_text(encoding="utf-8", errors="ignore")
    match = TITLE_PATTERN.search(content)

    if match:
        title = clean_text(match.group(1))
        if title:
            return title

    return fallback


def name_tokens(value: str) -> list[str]:
    return [token for token in slugify(value).split("-") if token]


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

        folder_name = site_dir.parent.name if site_dir.parent != root else site_dir.name
        display_name = read_display_name(index_path, folder_name)
        slug = slugify(folder_name)
        original_slug = slug
        counter = 2

        existing_slugs = {site["slug"] for site in sites}
        while slug in existing_slugs:
            slug = f"{original_slug}-{counter}"
            counter += 1

        sites.append(
            {
                "display_name": display_name,
                "name_slug": slugify(display_name),
                "slug": slug,
                "source": site_dir,
            }
        )

    sites = sorted(sites, key=lambda site: str(site["display_name"]).casefold())
    add_aliases(sites)
    return sites


def add_aliases(sites: list[dict[str, str | Path]]) -> None:
    prefix_options: dict[int, list[str]] = {}

    for index, site in enumerate(sites):
        tokens = name_tokens(str(site["display_name"]))
        prefix_options[index] = ["-".join(tokens[:length]) for length in range(1, len(tokens) + 1)]

    all_prefixes = [
        prefix
        for prefixes in prefix_options.values()
        for prefix in prefixes
    ]

    for index, site in enumerate(sites):
        aliases = {str(site["slug"]), str(site["name_slug"])}

        for prefix in prefix_options[index]:
            if all_prefixes.count(prefix) == 1:
                aliases.add(prefix)
                break

        site["aliases"] = sorted(alias for alias in aliases if alias)


def apply_custom_aliases(root: Path, sites: list[dict[str, str | Path]]) -> None:
    aliases_path = root / "docker" / "aliases.json"
    if not aliases_path.exists():
        return

    data = json.loads(aliases_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("docker/aliases.json must be a JSON object.")

    for site in sites:
        site["aliases"] = [str(site["slug"])]

    sites_by_slug = {
        str(site["slug"]): site
        for site in sites
    }
    sites_by_slug.update(
        {
            str(site["name_slug"]): site
            for site in sites
        }
    )

    for target, aliases in data.items():
        target_slug = slugify(str(target))
        site = sites_by_slug.get(target_slug)
        if site is None:
            valid_targets = ", ".join(sorted(sites_by_slug))
            raise ValueError(
                f"Unknown vCard target '{target}' in docker/aliases.json. "
                f"Valid targets are: {valid_targets}"
            )

        if isinstance(aliases, str):
            aliases = [aliases]

        if not isinstance(aliases, list):
            raise ValueError(
                f"Aliases for '{target}' must be a string or a list of strings."
            )

        current_aliases = set(site["aliases"])
        for alias in aliases:
            alias_slug = slugify(str(alias))
            if alias_slug:
                current_aliases.add(alias_slug)

        site["aliases"] = sorted(current_aliases)

    validate_aliases(sites)


def validate_aliases(sites: list[dict[str, str | Path]]) -> None:
    used_aliases: dict[str, str] = {}

    for site in sites:
        for alias in site["aliases"]:
            existing_site = used_aliases.get(alias)
            if existing_site:
                raise ValueError(
                    f"Alias '{alias}' is assigned to both '{existing_site}' "
                    f"and '{site['slug']}' in docker/aliases.json."
                )
            used_aliases[alias] = str(site["slug"])


def copy_site(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if item.name in IGNORED_DIRS or item.name in IGNORED_FILES:
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


def build_nginx_host_map(sites: list[dict[str, str | Path]]) -> str:
    alias_lines = []

    for site in sites:
        for alias in site["aliases"]:
            alias_lines.append(f"    {alias} {site['slug']};")

    prefix_lines = [
        f"    {site['slug']} /{site['slug']};"
        for site in sites
    ]

    return f"""# Generated by docker/build_vcards.py.
# Maps subdomains such as cesar.example.com to the vCard folder.
map $host $vcard_subdomain {{
    default "";
    ~^(?<vcard_first_label>[^.]+)\\..+$ $vcard_first_label;
}}

map $vcard_subdomain $vcard_slug {{
    default "";
{chr(10).join(alias_lines)}
}}

map $vcard_slug $vcard_prefix {{
    default "";
{chr(10).join(prefix_lines)}
}}
"""


def main() -> int:
    if len(sys.argv) not in {3, 4}:
        print("Usage: build_vcards.py <source-root> <output-root> [nginx-output-root]", file=sys.stderr)
        return 2

    source_root = Path(sys.argv[1]).resolve()
    output_root = Path(sys.argv[2]).resolve()
    nginx_output_root = Path(sys.argv[3]).resolve() if len(sys.argv) == 4 else None

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    if nginx_output_root:
        if nginx_output_root.exists():
            shutil.rmtree(nginx_output_root)
        nginx_output_root.mkdir(parents=True)

    sites = discover_sites(source_root)
    if not sites:
        print("No vCard sites with index.html were found.", file=sys.stderr)
        return 1
    apply_custom_aliases(source_root, sites)

    for site in sites:
        copy_site(Path(site["source"]), output_root / str(site["slug"]))

    public_sites = [
        {
            "name": str(site["display_name"]),
            "path": f"/{site['slug']}/",
            "host_aliases": site["aliases"],
        }
        for site in sites
    ]

    (output_root / "index.html").write_text(build_index(sites), encoding="utf-8")
    (output_root / "routes.json").write_text(
        json.dumps(public_sites, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if nginx_output_root:
        (nginx_output_root / "00-vcard-host-map.conf").write_text(
            build_nginx_host_map(sites),
            encoding="utf-8",
        )

    print(f"Built {len(sites)} vCard routes:")
    for site in sites:
        print(f"  /{site['slug']}/ ({', '.join(site['aliases'])}) <- {site['source']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
