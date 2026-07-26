# Local Scan Execution Guide — C2 First Live Run

**Why this exists:** the AI execution environment used for this project's validation work caps a single command at 45 seconds and doesn't keep background processes alive between steps. Your real `~/Downloads` folder has 1,107 top-level entries — at the ~2 files/second observed rate, a full scan needs roughly 9–10 minutes, which that environment can't sustain. Your own terminal has no such limit. This guide walks you through running `scan()` locally, so you get real, complete results, then bringing the output back here for analysis.

**What this does and doesn't do:** `scan()` only reads and hashes files in the top level of your configured Downloads folder (no subfolders, no recursion) and writes results to this project's own `Database/` and `Runtime/Logs/`. **It never moves, renames, or modifies anything in your Downloads folder.** Nothing beyond `scan()` is covered by this guide — do not run `execute` (the step that actually moves files) until you've reviewed results with me and separately decided to.

---

## 1. One-time setup

Open Terminal and go to the project folder:

```bash
cd ~/Desktop/"Download Intelligence"
```

Check your Python version (3.10+ recommended; this project has been tested on 3.10):

```bash
python3 --version
```

Install dependencies:

```bash
pip3 install -r requirements.txt
```

**Known issue you'll hit here, harmless but worth knowing about (already tracked as finding H1):** `requirements.txt` lists `PyYAML` twice, pinned to two different versions (`6.0.1` and `6.0.3`). `pip` will just use the last one it sees (`6.0.3`) without erroring — nothing to fix, just don't be alarmed if you notice the duplicate line.

If `pip3 install` fails on any single package, tell me which one and its error — some of these (`Pillow`, `pdfplumber`) occasionally need system-level image/PDF libraries depending on your macOS setup.

## 2. Reconfigure for your real machine

**Important:** the project's config currently points at paths from the AI tool's own sandboxed environment, not your real Mac. You need to reconfigure before scanning locally. Run:

```bash
python3 -m src.cli init
```

When prompted:
- **Downloads source path:** `/Users/vicky/Downloads` (your real Downloads folder)
- **destination_root:** `/Users/vicky/Desktop/Organized Downloads` (a new folder — `init` will ask to create it if it doesn't exist; a version of this was already created during our earlier session, so it should already exist)

Confirm it worked:

```bash
python3 -m src.cli config
```

You should see both real paths listed, not anything starting with `/sessions/...`.

## 3. Run the scan

```bash
python3 -m src.cli scan
```

This will run in your terminal for several minutes — let it finish completely. You'll see a running sense of progress isn't printed live (it prints one summary at the end), so it will look like nothing is happening; that's expected, not a hang. When it's done, it prints a summary: total entries seen, discovered count, skipped count with reasons.

**Do not Ctrl-C it partway through** — an interrupted scan currently loses all its progress (this is the exact issue we found and logged as TD-45 in `TECHNICAL_DEBT_REGISTER.md`; there's no partial-credit mechanism yet). If it's taking much longer than ~10-15 minutes, or you need to stop it, let it fail naturally or note how far it seemed to get rather than force-killing it repeatedly.

## 4. What to send back

Once it finishes, copy me:

1. **The full terminal output** from the `scan` command (the summary it prints).
2. **`Database/Metadata/metadata_store.json`** — either paste its contents (if not too large) or just tell me the file size / record count. You can get a quick count with:
   ```bash
   python3 -c "import json; print(len(json.load(open('Database/Metadata/metadata_store.json'))))"
   ```
3. **`Runtime/Logs/action_log.jsonl`** — same idea; a line count is a good starting point:
   ```bash
   wc -l Runtime/Logs/action_log.jsonl
   ```

I'll take it from there — read the results, produce the First Live Run Report (classification results, confidence distribution, duplicates, review queue, etc.), and hold at the preview stage exactly as before. No `execute` step happens without your separate, explicit go-ahead after we've looked at this together.

## 5. If something looks wrong

Stop and tell me rather than troubleshooting alone — especially:
- Any error message that mentions a real file path being unreadable/corrupted.
- The command exiting with a non-zero status before printing a summary.
- Anything that looks like it touched a file *inside* `~/Downloads` itself (it shouldn't — `scan` is read-only against your source folder by design).
