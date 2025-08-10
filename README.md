# M3U Unpacker

A tiny Python script that downloads an M3U playlist from a URL and splits it into **one `.m3u` file per channel**.

- Puts **all occurrences** of a channel into a **subfolder named after that channel**.
- Each file contains **exactly one** `#EXTINF` + URL pair.
- Duplicate occurrences use filenames like `Channel.m3u`, `Channel_2.m3u`, `Channel_3.m3u`, etc.
- Folder and file names are sanitized and truncated with `...` to avoid OS path issues.
- Channels without a name are skipped with a `WARNING` log.

# Setup
Install python3.12 and pipenv, then run:

```bash
pipenv install
```

# Usage
python3 main.py \
  --m3u-url "https://example.com/playlist.m3u" \
  --m3u-unpack-folder "./m3u-folder"
