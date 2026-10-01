# Discord Music Bot

Python Discord bot with:

- `/play` and `/vplay`
- YouTube search/URLs
- Spotify track/playlist/album URL resolution to YouTube searches
- `/pause`, `/start`, `/stop`, `/skip`
- `/queue`, `/shuffle`, `/nowplaying`
- `/seek`, `/seekback`
- `/speed`
- `/ping`, `/id`
- `/channeladd`
- `/auth`, `/unauth`, `/admins`
- `/broadcast` — sends the announcement in the server channel and attempts to DM all non-bot members
- `/gban`
- `/tagall`
- `/help`

## 1. Discord bot

Create a bot in the Discord Developer Portal and copy its token.

Enable these privileged intents if you use the member features:

- Server Members Intent
- Message Content Intent

Invite the bot with the `bot` and `applications.commands` scopes. Give it View Channel, Send Messages, Connect, Speak, and Ban Members as needed.

## 2. Local setup

Install Python 3.12 and FFmpeg.

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill:

```env
DISCORD_TOKEN=...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
```

Run:

```bash
python bot.py
```

## 3. Render

This repository includes `render.yaml`.

Create a Background Worker from the GitHub repository. The worker installs FFmpeg and starts with:

```bash
python bot.py
```

Add the three environment variables in Render.

## Commands

Music:
`/play`, `/vplay`, `/start`, `/pause`, `/stop`, `/skip`, `/queue`, `/shuffle`, `/speed`, `/seek`, `/seekback`, `/nowplaying`

Server:
`/channeladd`, `/auth`, `/unauth`, `/admins`, `/broadcast`, `/gban`, `/tagall`, `/id`, `/ping`, `/help`

### Notes

- Spotify does not provide a general Discord voice audio stream. Spotify links are resolved to track/artist searches and played from YouTube.
- `/seek` and `/seekback` restart the FFmpeg stream at an approximate position.
- `/speed` supports 0.5x–2.0x.
- Authorization and channel settings are in-memory in this starter project. They reset when the process restarts. For permanent settings, add a database later.
- Do not commit `.env` or your bot token to GitHub.
\n### Broadcast behavior\n\n`/broadcast` posts the announcement in the server and attempts to send the same notification by DM to every non-bot member. Members who have blocked the bot, disabled server-member DMs, or otherwise cannot receive DMs are skipped. Discord rate limits can also affect large servers.\n