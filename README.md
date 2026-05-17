# 🎟️ Ticket Exchange Bot

A Discord bot for exchanging university sports tickets with other members of the server.

---

## Overview

The Ticket Exchange Bot lets you post tickets you have available or find tickets you're looking for. When a match is found between a have and a want, the bot will ping you automatically.

All listings are posted to the dedicated ticket exchange channel, but you can use the commands from anywhere in the server.

---

## Commands

### `/have` — Post tickets you have available

Use this when you have tickets you want to give away or sell.

**Required fields:**
- **Sport** — choose from Football, Men's Basketball, Women's Basketball, or Volleyball
- **Month** — the month of the game (1–12)
- **Day** — the day of the game (1–31)
- **Year** — the year of the game
- **Hour** — the start time in 24-hour format (0–23)
- **Minute** — choose from 00, 15, 30, or 45
- **Quantity** — number of tickets available

**Optional fields:**
- **Notes** — any extra info such as section, row, or asking price

---

### `/want` — Post that you're looking for tickets

Use this when you're looking for tickets to a game. You can be as specific or as general as you like — only sport is required.

**Required fields:**
- **Sport** — choose from Football, Men's Basketball, Women's Basketball, or Volleyball

**Optional fields:**
- **Month**, **Day**, **Year**, **Hour**, **Minute** — specify a particular game (all or none)
- **Quantity** — number of tickets you need
- **Notes** — anything else worth mentioning

> If you don't specify a date, your listing will match with any available tickets for that sport.

---

### `/close` — Close one of your listings

Use this when your tickets have been exchanged or you no longer need to post the listing.

Running `/close` will show you a dropdown of all your active listings. Select the one you want to close and it will be marked as closed in the channel.

---

## How Matching Works

Every time a listing is posted, the bot automatically searches for matching listings from other users:

- A `/have` will match any `/want` for the same sport where either no date was specified or the dates match
- A `/want` will match any `/have` for the same sport where dates match or the want has no date

When a match is found, the bot pings the matched user in the ticket exchange channel so they know to reach out.

**Once you've arranged the exchange**, the original poster should run `/close` to remove their listing.

---

## Listing Expiry

Listings expire automatically:

- **Have listings** expire after the game date and time has passed
- **Want listings** expire after 6 months

Expired listings are removed automatically — no action needed on your part.

---

## Tips

- Use the **Notes** field to include your contact preference, asking price, or seat location
- If you're flexible on the game, post a `/want` with no date — you'll match with any available tickets for that sport
- Close your listing once the exchange is done so others know it's no longer available
- You can have multiple active listings at the same time
