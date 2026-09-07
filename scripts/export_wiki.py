"""Export reviewed Wiki sources to a separate directory; never push or commit."""
import argparse
from pathlib import Path
import re
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "wiki"
LINK = re.compile(r"(\[[^\]]*\]\()([^)]+)(\))")


def render(document, ref):
    def replace(match):
        target = match[2]
        path, separator, fragment = target.partition("#")
        if not path or "://" in path or path.startswith("mailto:"):
            return match[0]
        resolved = (document.parent / unquote(path)).resolve()
        if not resolved.is_file() or not resolved.is_relative_to(ROOT):
            raise ValueError(f"{document.name}: invalid local file link {target}")
        suffix = separator + fragment
        if resolved.parent == SOURCE:
            url = quote(resolved.stem) + suffix
        else:
            url = ("https://github.com/FlightDan/dispatcher-sdk/blob/"
                   + quote(ref, safe="") + "/"
                   + quote(resolved.relative_to(ROOT).as_posix(), safe="/") + suffix)
        return match[1] + url + match[3]
    return LINK.sub(replace, document.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ref", required=True,
                        help="Published repository commit, tag or branch for API links")
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination == ROOT or destination.is_relative_to(ROOT) or ROOT.is_relative_to(destination):
        parser.error("output must be outside the source checkout and its ancestors")
    if not args.ref.strip():
        parser.error("ref must not be empty")
    if destination.exists() and any(destination.iterdir()):
        parser.error("output must be a new or empty directory")
    # Render everything before writing, so invalid links produce no partial export.
    pages = {p.name: render(p, args.ref) for p in sorted(SOURCE.glob("*.md"))}
    if not pages:
        parser.error("no Wiki sources found")
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in pages.items():
        (destination / name).write_text(content, encoding="utf-8")
    print(f"Exported {len(pages)} pages to {destination}; repository ref: {args.ref}")
    print("Local export only. Verify that the referenced revision is published before pushing the Wiki.")


if __name__ == "__main__":
    main()
