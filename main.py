import argparse
import requests
import os
import re
import logging
from collections import defaultdict

# Log only warnings/errors
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# Independent limits so folders stay shorter than files
MAX_FOLDER_CHARS = 80
MAX_FILE_BASENAME_CHARS = 120  # before ".m3u"

def safe_name(s: str) -> str:
    """Sanitize and normalize a string for file/folder usage."""
    s = s.replace("\u00A0", " ")  # non-breaking spaces
    s = re.sub(r'[\\/*?:"<>|]', "_", s)  # illegal path chars
    s = re.sub(r"\s+", " ", s).strip()
    return s or "unknown"

def truncate_with_ellipsis(stem: str, limit: int) -> str:
    """Truncate to 'limit' chars, adding '...' if needed."""
    if len(stem) > limit:
        return stem[: max(1, limit - 3)].rstrip() + "..."
    return stem

def build_channel_output_path(base_dir: str, channel_stem: str, seq: int) -> str:
    """
    Put ALL occurrences into a subfolder:
      <base>/iptv/<safe_channel_folder>/<safe_channel_filename[ _n]>.m3u
    """
    folder = truncate_with_ellipsis(channel_stem, MAX_FOLDER_CHARS)
    subdir = os.path.join(base_dir, "iptv", folder)
    os.makedirs(subdir, exist_ok=True)

    file_stem = f"{channel_stem}_{seq}" if seq > 1 else channel_stem
    file_stem = truncate_with_ellipsis(file_stem, MAX_FILE_BASENAME_CHARS)

    return os.path.join(subdir, f"{file_stem}.m3u")

def build_keyword_output_path(base_dir: str, keyword: str) -> str:
    """
    Keyword aggregate file lives directly under base_dir:
      <base>/<safe_keyword>.m3u
    """
    stem = truncate_with_ellipsis(safe_name(keyword), MAX_FILE_BASENAME_CHARS)
    return os.path.join(base_dir, f"{stem}.m3u")

def main():
    parser = argparse.ArgumentParser(
        description="Download M3U and unpack into per-channel files; aggregate by --keyword."
    )
    parser.add_argument("--m3u-url", required=True, help="URL to the M3U file")
    parser.add_argument("--m3u-unpack-folder", required=True, help="Base folder to write outputs")
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Keyword to aggregate channels by name into <keyword>.m3u (can be used multiple times)",
    )
    args = parser.parse_args()

    # Download M3U
    resp = requests.get(args.m3u_url)
    resp.raise_for_status()
    lines = resp.text.splitlines()

    # Ensure base and iptv folders
    base_dir = args.m3u_unpack_folder
    os.makedirs(os.path.join(base_dir, "iptv"), exist_ok=True)

    # Prep keyword matching (case-insensitive, preserve order, de-dup)
    seen = set()
    keywords = []
    for k in args.keyword:
        k_norm = k.strip()
        if not k_norm:
            continue
        key = k_norm.lower()
        if key not in seen:
            seen.add(key)
            keywords.append(k_norm)  # keep original casing for filename

    # Aggregation store: keyword(lower) -> list of blocks (each block is [EXTINF, URL])
    keyword_blocks = {k.lower(): [] for k in keywords}

    # Per-channel outputs
    name_counts = defaultdict(int)
    current_block = []
    channel_name = None

    for line in lines:
        if line.startswith("#EXTINF"):
            current_block = [line]
            if "," in line:
                channel_name = safe_name(line.split(",", 1)[1])
            else:
                channel_name = "unknown"
        elif line.strip() and not line.startswith("#"):
            current_block.append(line)
            if channel_name and channel_name != "unknown":
                # Write per-channel single-entry file under base/iptv/<Channel>/
                name_counts[channel_name] += 1
                seq = name_counts[channel_name]
                out_path = build_channel_output_path(base_dir, channel_name, seq)
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(current_block) + "\n")
                except OSError as e:
                    logging.warning("Failed to write %s: %s", out_path, e)

                # Collect into keyword files (channel can match multiple keywords)
                if keywords:
                    lower_name = channel_name.lower()
                    for kw in keywords:
                        if kw.lower() in lower_name:
                            # store a copy of the block
                            keyword_blocks[kw.lower()].append(list(current_block))
            else:
                logging.warning("Skipping unknown channel for URL: %s", line)

            current_block = []
            channel_name = None

    # Write keyword aggregate files
    for kw in keywords:
        blocks = keyword_blocks.get(kw.lower(), [])
        if not blocks:
            continue
        kw_path = build_keyword_output_path(base_dir, kw)
        try:
            with open(kw_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for block in blocks:
                    f.write("\n".join(block) + "\n")
        except OSError as e:
            logging.warning("Failed to write keyword file %s: %s", kw_path, e)

if __name__ == "__main__":
    main()
