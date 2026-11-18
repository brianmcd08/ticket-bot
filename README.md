# 🎟️ Ticket Exchange Bot

A Discord bot for exchanging university sports tickets with other members of the server.

---

## What It Does

The Ticket Exchange Bot lets you post tickets you have available or find tickets you're looking for. When a match is found between someone who has tickets and someone who wants them, the bot pings both of you automatically so you can connect.

All listings are posted in the ticket-exchange channel (`CHANNEL_ID`), and you can run commands from anywhere in the server. Members choose which sports ping them with the buttons `/rolepanel` posts; a new listing pings its sport's role. `/listings`, `/mine`, and `/help` reply privately, visible only to you, in whatever channel you run them.

---

## Commands

### `/have` — Post tickets you have available

Use this when you have tickets you want to give away or sell.

**Required:**
- **Month**, **Day**, **Year** — the date of the game
- **Quantity** — number of tickets

**Optional:**
- **Sport** — Football, Men's Basketball, Women's Basketball, Volleyball, or Baseball. Can be left blank when you run the command inside a sport's channel; it's taken from the channel. If the channel doesn't say (or covers both basketball teams), the bot asks with a dropdown.
- **Notes** — game time, section, row, asking price, or anything else useful

> Listings are identified by the game date. There's no start time field, since matching works on the day; put the tip-off time in **Notes** if it matters.

---

### `/want` — Post that you're looking for tickets

Use this when you need tickets to a game. Nothing is required if you run it inside a sport's channel; be as specific or open-ended as you like.

**Optional:**
- **Sport** — Football, Men's Basketball, Women's Basketball, Volleyball, or Baseball. Can be left blank inside a sport's channel.
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

Shows active haves and wants grouped by type. Only visible to you, in whatever channel you run it.

Scoped to the channel you run it in: in the volleyball channel you see volleyball, in the basketball channel you see both men's and women's. Run it anywhere else, or in the general channel, to see everything.

**Optional:**
- **Sport** — filter to one sport, overriding the channel

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

### `/rolepanel` — Post the sport notification buttons

Run it in the channel where members should pick their roles. It creates any missing sport roles (Football, Men's Basketball, Women's Basketball, Volleyball, Baseball) and posts a message with one button per sport; tapping a button adds or removes that role. A new listing pings its sport's role, and live scores will too.

The bot needs the **Manage Roles** permission, and its own role must sit **above** the sport roles in Server Settings → Roles (new roles are created at the bottom, so this is normally already true). The buttons keep working after restarts. Running it again posts a fresh panel and recreates any role that was deleted; delete the old panel message yourself.

---

### `/reopen <listing_id>` — Put a closed listing back

Restricted to server administrators and hidden from `/help`.

Use this when someone's listing was closed and they want it back, typically after a `/clear`. Because closing only flips a status flag, nothing is ever lost: the listing keeps its original owner, sport, date, quantity and notes.

**Where to find the ID:** it's on the listing's post, in the footer, as `Listing ID: 7`. That footer survives closing, so you can read it straight off the greyed-out post. It also appears as `(#7)` in `/listings`.

Reopening restores the original post in place (un-greying it), then adds a short message pinging the owner with a link to it, since the restored post may be far up the channel. If the original post was deleted, a fresh one is posted instead. Matching runs again, so a reopened listing pairs up with anything that already fits it.

---

### `/refresh` — Re-render active listing posts

Restricted to server administrators and hidden from `/help`.

A listing's card is built when it is posted, so a change to the card layout only affects listings posted afterwards. `/refresh` re-renders every active listing's post from its database row, bringing already-posted cards up to the current layout.

It edits posts in place and nothing else: no announcement, no pings, no reposting of cards whose message was deleted, and matching is **not** re-run. The reply is a private count of what was updated and what was skipped, and why.

---

## How Matching Works

Every time a listing is posted, the bot automatically searches for matches:

- A `/have` matches any `/want` for the same sport on the same game day, or any `/want` with no date specified
- A `/want` matches any `/have` for the same sport on the same game day

Every posted card ends with the command that matches it, so a reader knows the next step without having read `/help`: a **have** card says to post `/want` for that game, a **want** card says to post `/have`. Replying in the channel or DMing the poster does not create a match. Closing a listing removes that prompt from its card, since a closed listing can no longer match.

Matching is on the calendar day. You never match with your own listings.

When a match is found, the bot pings both users in the ticket-exchange channel (a match is always within one sport). From there, it's up to you to reach out and arrange the exchange.

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
- **On your phone:** after typing `/have`, tap the command in the menu that pops up. Pressing return sends it as a plain message instead; the bot will reply with a reminder if that happens
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
   SCORES_CHANNEL_ID=

   FOOTBALL_CHANNEL_ID=
   BASKETBALL_CHANNEL_ID=
   VOLLEYBALL_CHANNEL_ID=
   BASEBALL_CHANNEL_ID=
   DEFAULT_SPORT_CHANNEL_ID=
   ```
   New listings always go to `CHANNEL_ID`. The per-sport channel IDs are used to fill in the sport when `/have` or `/want` is run inside that channel, and to find listing posts made before listings moved to one channel, so keep them set. Any left blank fall back to `DEFAULT_SPORT_CHANNEL_ID`, and if that is blank too, to `CHANNEL_ID` — so an incomplete `.env` degrades to single-channel behaviour instead of failing to start. The resolved routing is printed at startup; check it with `journalctl -u ticket-bot`.

   `SCORES_CHANNEL_ID` is where live scores will be posted; leave it blank and no scores are posted.

   `CHANNEL_ID` is also used for server-wide announcements, such as the notice `/clear` posts.

   The bot needs View Channel, Send Messages, Embed Links, and Read Message History in the ticket-exchange channel (and in any sport channel that still has older listing posts), plus **Manage Roles** for `/rolepanel`. Members need Use Application Commands.

   In the [Developer Portal](https://discord.com/developers/applications), under **Bot → Privileged Gateway Intents**, turn on **Message Content Intent**. The bot uses it to notice a `/have` that a phone sent as plain text and reply with a hint. Without it the bot fails to log in.
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

### Testing locally

`.env` holds the real bot's settings, so don't run the bot from it on your own machine: two copies on one token both answer every command. Instead, use a separate test bot in a private test server:

1. Create the test server and a few channels (include one shared basketball channel).
2. In the Developer Portal, create a second application, copy its bot token, and turn on **Message Content Intent**.
3. Invite it via **OAuth2 → URL Generator** with the `bot` and `applications.commands` scopes and the permissions listed above.
4. Fill in `.env.dev` (gitignored) with the test token, server ID and channel IDs, with `DB_PATH=dev.db`.
5. Run it:
   ```bash
   TICKETBOT_ENV=.env.dev uv run python bot.py
   ```
   The startup line shows which config file was loaded.

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
