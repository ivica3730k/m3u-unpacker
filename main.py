import argparse
import requests
import os
import re
import logging
from collections import defaultdict

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

MAX_FOLDER_CHARS = 80
MAX_FILE_BASENAME_CHARS = 120  # before ".m3u"

def safe_name(s: str) -> str:
    s = s.replace("\u00A0", " ")
    s = re.sub(r'[\\/*?:"<>|]', "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "unknown"

def truncate_with_ellipsis(stem: str, limit: int) -> str:
    if len(stem) > limit:
        return stem[: max(1, limit - 3)].rstrip() + "..."
    return stem

def build_channel_output_path(base_dir: str, channel_stem: str, seq: int) -> str:
    folder = truncate_with_ellipsis(channel_stem, MAX_FOLDER_CHARS)
    subdir = os.path.join(base_dir, "iptv", folder)
    os.makedirs(subdir, exist_ok=True)

    file_stem = f"{channel_stem}_{seq}" if seq > 1 else channel_stem
    file_stem = truncate_with_ellipsis(file_stem, MAX_FILE_BASENAME_CHARS)

    return os.path.join(subdir, f"{file_stem}.m3u")

def build_keyword_output_path(base_dir: str, keyword: str) -> str:
    stem = truncate_with_ellipsis(safe_name(keyword), MAX_FILE_BASENAME_CHARS)
    return os.path.join(base_dir, f"{stem}.m3u")

def compile_keyword_patterns(keywords):
    """Return dict of lowercase keyword -> compiled regex for whole word matching."""
    patterns = {}
    for kw in keywords:
        pattern = r"\b" + re.escape(kw) + r"\b"
        patterns[kw.lower()] = re.compile(pattern, re.IGNORECASE)
    return patterns

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
        help="Keyword to aggregate channels by name into <keyword>.m3u "
             "(whole word match, case-insensitive, can be used multiple times)",
    )
    args = parser.parse_args()

    resp = requests.get(args.m3u_url)
    resp.raise_for_status()
    lines = resp.text.splitlines()

    base_dir = args.m3u_unpack_folder
    os.makedirs(os.path.join(base_dir, "iptv"), exist_ok=True)

    # Normalize keyword list and prepare regex patterns
    keyword_map = {}  # lowercase -> original
    for k in args.keyword:
        k_clean = k.strip()
        if k_clean:
            key_lower = k_clean.lower()
            if key_lower not in keyword_map:
                keyword_map[key_lower] = k_clean
    keyword_patterns = compile_keyword_patterns(keyword_map.values())

    keyword_blocks = {k: [] for k in keyword_map.keys()}

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
                name_counts[channel_name] += 1
                seq = name_counts[channel_name]
                out_path = build_channel_output_path(base_dir, channel_name, seq)
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(current_block) + "\n")
                except OSError as e:
                    logging.warning("Failed to write %s: %s", out_path, e)

                # Whole-word keyword match
                for kw_lower, pattern in keyword_patterns.items():
                    if pattern.search(channel_name):
                        keyword_blocks[kw_lower].append(list(current_block))
            else:
                logging.warning("Skipping unknown channel for URL: %s", line)

            current_block = []
            channel_name = None

    # Write keyword aggregate files
    for kw_lower, blocks in keyword_blocks.items():
        if not blocks:
            continue
        kw_path = build_keyword_output_path(base_dir, keyword_map[kw_lower])
        try:
            with open(kw_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for block in blocks:
                    f.write("\n".join(block) + "\n")
        except OSError as e:
            logging.warning("Failed to write keyword file %s: %s", kw_path, e)

if __name__ == "__main__":
    main()
