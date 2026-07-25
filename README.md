# 🎟️ Ticket Exchange Bot

A Discord bot for exchanging university sports tickets with other members of the server.

---

## What It Does

The Ticket Exchange Bot lets you post tickets you have available or find tickets you're looking for. When a match is found between someone who has tickets and someone who wants them, the bot pings both of you automatically so you can connect.

All listings are posted to the dedicated ticket exchange channel, but you can run commands from anywhere in the server. `/listings`, `/mine`, and `/help` reply privately, visible only to you, in whatever channel you run them.

---

## Commands

### `/have` — Post tickets you have available

Use this when you have tickets you want to give away or sell.

**Required:**
- **Sport** — Football, Men's Basketball, Women's Basketball, or Volleyball
- **Month**, **Day**, **Year** — the date of the game
- **Quantity** — number of tickets

**Optional:**
- **Notes** — game time, section, row, asking price, or anything else useful

> Listings are identified by the game date. There's no start time field, since matching works on the day; put the tip-off time in **Notes** if it matters.

---

### `/want` — Post that you're looking for tickets

Use this when you need tickets to a game. Only sport is required — you can be as specific or open-ended as you like.

**Required:**
- **Sport** — Football, Men's Basketball, Women's Basketball, or Volleyball

**Optional:**
- **Month**, **Day**, **Year** — specify a particular game (provide all three or none)
- **Quantity** — number of tickets you need
- **Notes** — anything else worth mentioning

> **Tip:** If you leave the date blank, your listing will match with any available tickets for that sport — great if you're flexible on the game.

---

### `/close` — Close one of your listings

Use this once your tickets have been exchanged or if you change your mind.

Running `/close` shows a dropdown of all your active listings. Select the one you want to close and it will be marked as closed.

---

### `/listings` — See all open listings

Shows every active have and want in the server, grouped by type. Only visible to you, in whatever channel you run it.

**Optional:**
- **Sport** — filter to just one sport

---

### `/mine` — See your own open listings

Shows just the haves and wants you currently have posted. Only visible to you, in whatever channel you run it.

---

### `/help` — Get help on how to use the ticket exchange

Shows a summary of all commands. Only visible to you, in whatever channel you run it.

---

## Admin Commands

### `/clear` — Close every open listing

Restricted to server administrators and hidden from `/help` and from the command picker for everyone else.

Closes all active listings server-wide, for every user, and greys out their channel posts as `❌ CLOSED`. Shows a confirmation prompt with the count first, and the confirmation expires after two minutes if ignored. Rows are closed rather than deleted, so nothing is lost from the database.

Useful for resetting between seasons, or after testing.

---

## How Matching Works

Every time a listing is posted, the bot automatically searches for matches:

- A `/have` matches any `/want` for the same sport on the same game day, or any `/want` with no date specified
- A `/want` matches any `/have` for the same sport on the same game day

Matching is on the calendar day. You never match with your own listings.

When a match is found, the bot pings both users in the ticket exchange channel. From there, it's up to you to reach out and arrange the exchange.

Matched listings stay open and keep showing up in `/listings` and `/mine`. Once the exchange is actually done, run `/close` to remove your listing.

---

## Listing Expiry

Listings expire automatically — no action needed on your part:

- **Have listings** expire the day after the game
- **Want listings** expire after 6 months

---

## Tips

- Use **Notes** to share your contact preference, seat location, or asking price
- You can have multiple active listings at the same time
- Close your listing once the exchange is done so others know it's taken
- If you're flexible on the game, skip the date fields in `/want` — you'll match with any available tickets for that sport

---

## Deployment

The bot is designed to run as a `systemd` service (e.g. on a Raspberry Pi).

### First-time setup

1. Clone the repo onto the machine:
   ```bash
   git clone <repo-url> ~/ticket-bot
   cd ~/ticket-bot
   ```
2. Install [uv](https://docs.astral.sh/uv/) if it isn't already present:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Create `.env` in the project root (it's gitignored — copy it over separately, e.g. with `scp`). Use `example.env` as a template:
   ```
   DISCORD_TOKEN=
   GUILD_ID=
   CHANNEL_ID=
   DB_PATH=tickets.db
   ```
4. Install dependencies. This also downloads a matching Python (>=3.12) if the system Python is older:
   ```bash
   uv sync
   ```
5. Install the service. Edit `deploy/ticket-bot.service` first — set `User` to your username and update `WorkingDirectory`/`ExecStart` to match your clone path:
   ```bash
   sudo cp deploy/ticket-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now ticket-bot
   ```

### Day-to-day

- **View logs:** `journalctl -u ticket-bot -f`
- **Restart:** `sudo systemctl restart ticket-bot`
- **Stop:** `sudo systemctl stop ticket-bot`
- **Deploy a code change:**
  ```bash
  git pull
  uv sync
  sudo systemctl restart ticket-bot
  ```
  If `deploy/ticket-bot.service` itself changed, re-copy it and run `daemon-reload` before restarting.

The service starts on boot (after network connectivity is available) and auto-restarts on crash.
