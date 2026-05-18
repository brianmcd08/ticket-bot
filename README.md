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
