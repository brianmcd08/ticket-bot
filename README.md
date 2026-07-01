# 🎟️ Ticket Exchange Bot

A Discord bot for exchanging university sports tickets with other members of the server.

---

## What It Does

The Ticket Exchange Bot lets you post tickets you have available or find tickets you're looking for. When a match is found between someone who has tickets and someone who wants them, the bot pings both of you automatically so you can connect.

All listings are posted to the dedicated ticket exchange channel, but you can run commands from anywhere in the server.

---

## Commands

### `/have` — Post tickets you have available

Use this when you have tickets you want to give away or sell.

**Required:**
- **Sport** — Football, Men's Basketball, Women's Basketball, or Volleyball
- **Month**, **Day**, **Year** — the date of the game
- **Hour** — game start time in 24-hour format (e.g. 13 for 1:00 PM)
- **Minute** — choose from 00, 15, 30, or 45
- **Quantity** — number of tickets

**Optional:**
- **Notes** — section, row, asking price, or anything else useful

---

### `/want` — Post that you're looking for tickets

Use this when you need tickets to a game. Only sport is required — you can be as specific or open-ended as you like.

**Required:**
- **Sport** — Football, Men's Basketball, Women's Basketball, or Volleyball

**Optional:**
- **Month**, **Day**, **Year**, **Hour**, **Minute** — specify a particular game (provide all fields or none)
- **Quantity** — number of tickets you need
- **Notes** — anything else worth mentioning

> **Tip:** If you leave the date blank, your listing will match with any available tickets for that sport — great if you're flexible on the game.

---

### `/close` — Close one of your listings

Use this once your tickets have been exchanged or you no longer need the listing.

Running `/close` shows a dropdown of all your active listings. Select the one you want to close and it will be marked as closed.

---

### `/listings` — See all open listings

Shows every active have and want in the server, grouped by type. Only visible to you.

**Optional:**
- **Sport** — filter to just one sport

---

### `/mine` — See your own open listings

Shows just the haves and wants you currently have posted. Only visible to you.

---

### `/help` — Post and pin the command list

Posts a summary of all commands to the ticket exchange channel and pins it, unpinning any previous help message first so there's only ever one. Visible to everyone in the channel.

> **Note:** the bot needs the **Manage Messages** permission to pin. If it's missing, `/help` will still post the summary but let you know it couldn't pin it.

---

## How Matching Works

Every time a listing is posted, the bot automatically searches for matches:

- A `/have` matches any `/want` for the same sport where dates match or the want has no date specified
- A `/want` matches any `/have` for the same sport where the dates match

When a match is found, the bot pings both users in the ticket exchange channel. From there, it's up to you to reach out and arrange the exchange.

Once the exchange is done, run `/close` to remove your listing.

---

## Listing Expiry

Listings expire automatically — no action needed on your part:

- **Have listings** expire when the game date and time has passed
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
