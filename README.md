# Life Manager

A personal operating system I built for myself — and use every day — covering
journaling, personal finance, marathon training, and publishing my newsletter.

**This repo is a read-only demo.** The production app runs privately because it
contains my actual financial data and journals. What you see here mirrors the
real interface with sample data.

🔗 Live output of the system: [noesarc.com](https://noesarc.com) — my newsletter,
written by me, published through Life Manager's pipeline.

## What it does

- **Finance** — imports broker exports (Bolero CSVs), tracks my portfolio and
  budget in SQLite.
- **Training** — my marathon plan (October 2026), flexible, synchronized with the Garmin API for trustworthy metrics from my smartwatch.
- **Journaling** — daily entries, habit tracking, which doubles as context for AI features when needed.
- **Publishing** — writes, stages, and mirrors newsletter issues to the
  Next.js site behind noesarc.com.
- **Accommodation Hunt** — a watchlist of accommodations in Brussels that fit my profile and needs.

## How it's built

- Flask + Jinja2 server-rendered templates, vanilla JS — no frontend framework
- SQLite for all persistent data
- Automation pipelines for broker-export ingestion (Bolero PDF/CSV), bank
  statement imports, Garmin activity sync, and scheduled jobs (weekly AI
  review, database backups) via Windows Task Scheduler
- Built AI-first: large parts of this app were shipped with Claude Code as
  pair-builder. The app is also my testbed for integrating AI features
  end to end before I trust them with real data.

## Screenshots

<img width="1722" height="1132" alt="Screenshot 2026-07-12 103732" src="https://github.com/user-attachments/assets/c739fbec-654f-404f-9c99-d1f91a2c146b" />
<img width="1760" height="1682" alt="Screenshot 2026-07-12 103832" src="https://github.com/user-attachments/assets/ce25db1e-3d98-4b2b-b4db-385a3e54221a" />
<img width="1775" height="1821" alt="Screenshot 2026-07-12 103820" src="https://github.com/user-attachments/assets/8abf5c89-bbbe-403f-9357-05de90c9cf0c" />
<img width="1708" height="1602" alt="Screenshot 2026-07-12 103806" src="https://github.com/user-attachments/assets/07a52d7e-ab4f-483c-bf6d-801603c199f3" />


## Why it exists

I wanted one place where my systems live instead of ten subscriptions — and a
sandbox where I can build with AI on problems I actually have. This project motivated me to create an internal AI Assistant for Fenris Creations.
