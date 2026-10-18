# instagram-auto-publisher (@ft.prashu autopilot)

- `content/bank.json` - queue of posts (carousels + Reels), built by `tools/build_bank.py`
- `render.py` - draws every slide and Reel automatically (no manual design)
- `autopilot.py` - publishes the next post daily (7 PM IST) and writes `reports/latest.md` every Sunday
- `.github/workflows/autopilot.yml` - the schedule
- Secrets needed: `IG_ACCESS_TOKEN`, `IG_USER_ID` (GitHub repo secrets only, never in files)
