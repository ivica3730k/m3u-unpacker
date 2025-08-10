import argparse
import requests
import os
import re
import logging
from collections import defaultdict

# Log only warnings/errors, per your request
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# Independent limits so folders stay shorter than files
MAX_FOLDER_CHARS = 80
MAX_FILE_BASENAME_CHARS = 120  # before ".m3u"

def safe_name(name: str) -> str:
    """Sanitize and normalize a string for file/folder usage."""
    name = name.replace("\u00A0", " ")  # non-breaking spaces
    name = re.sub(r'[\\/*?:"<>|]', "_", name)  # illegal path chars
    name = re.sub(r"\s+", " ", name).strip()
    return name or "unknown"

def truncate_with_ellipsis(stem: str, limit: int) -> str:
    """Truncate to 'limit' chars, adding '...' if needed."""
    if len(stem) > limit:
        return stem[: max(1, limit - 3)].rstrip() + "..."
    return stem

def build_output_path(base_dir: str, channel_stem: str, seq: int) -> str:
    """
    Put ALL occurrences into a subfolder:
      <base>/<safe_channel_folder>/<safe_channel_filename[ _n]>.m3u
    """
    # Folder name: sanitized + truncated to folder limit
    folder = truncate_with_ellipsis(channel_stem, MAX_FOLDER_CHARS)
    subdir = os.path.join(base_dir, folder)
    os.makedirs(subdir, exist_ok=True)

    # File stem: full channel name (plus _n for duplicates) with its own limit
    file_stem = f"{channel_stem}_{seq}" if seq > 1 else channel_stem
    file_stem = truncate_with_ellipsis(file_stem, MAX_FILE_BASENAME_CHARS)

    return os.path.join(subdir, f"{file_stem}.m3u")

def main():
    parser = argparse.ArgumentParser(description="Download M3U and unpack into per-channel subfolders with safe names.")
    parser.add_argument("--m3u-url", required=True, help="URL to the M3U file")
    parser.add_argument("--m3u-unpack-folder", required=True, help="Folder to store unpacked M3U files")
    args = parser.parse_args()

    resp = requests.get(args.m3u_url)
    resp.raise_for_status()
    lines = resp.text.splitlines()

    os.makedirs(args.m3u_unpack_folder, exist_ok=True)

    name_counts = defaultdict(int)
    current_block = []
    channel_name = None

    for line in lines:
        if line.startswith("#EXTINF"):
            current_block = [line]
            # Channel name is text after the first comma
            if "," in line:
                channel_name = safe_name(line.split(",", 1)[1])
            else:
                channel_name = "unknown"
        elif line.strip() and not line.startswith("#"):
            current_block.append(line)
            if channel_name and channel_name != "unknown":
                name_counts[channel_name] += 1
                seq = name_counts[channel_name]
                out_path = build_output_path(args.m3u_unpack_folder, channel_name, seq)
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(current_block) + "\n")
                except OSError as e:
                    logging.warning("Failed to write %s: %s", out_path, e)
            else:
                logging.warning("Skipping unknown channel for URL: %s", line)
            current_block = []
            channel_name = None

if __name__ == "__main__":
    main()
