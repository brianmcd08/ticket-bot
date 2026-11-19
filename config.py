import os

from dotenv import dotenv_values

import channels
import espn


class Config:
    def __init__(self):
        # The Pi runs on .env (the real bot). Locally, point at the test bot
        # with TICKETBOT_ENV=.env.dev so a second copy of the live bot never
        # starts by accident.
        self.env_file = os.environ.get("TICKETBOT_ENV", ".env")
        if not os.path.isfile(self.env_file):
            raise SystemExit(f"Config file {self.env_file!r} not found")
        env = dotenv_values(self.env_file)

        db_path = env.get("DB_PATH")
        guild_str = env.get("GUILD_ID")
        channel_str = env.get("CHANNEL_ID")
        token = env.get("DISCORD_TOKEN")

        assert db_path, "Missing DB_PATH in " + self.env_file
        assert guild_str, "Missing GUILD_ID in " + self.env_file
        assert channel_str, "Missing CHANNEL_ID in " + self.env_file
        assert token, "Missing DISCORD_TOKEN in " + self.env_file

        self.db_path = db_path
        self.guild_id = int(guild_str)
        self.channel_id = int(channel_str)
        self.token = token

        # Where live scores are posted (scoreboard part 2). Optional: blank
        # means scores are simply not posted.
        scores_str = env.get("SCORES_CHANNEL_ID")
        self.scores_channel_id = int(scores_str) if scores_str else None
        # Whose matches to follow, by ESPN team id. Blank means Pitt; on the
        # dev server, set it to any team playing today to test live scores.
        self.scores_team_id = env.get("SCORES_TEAM_ID") or espn.PITT_TEAM_ID

        # Per-sport routing. Missing entries fall back rather than failing
        # startup; bot.py logs the resolved table so gaps stay visible.
        self.sport_channels = channels.build(
            channel_id=self.channel_id,
            football=env.get("FOOTBALL_CHANNEL_ID"),
            basketball=env.get("BASKETBALL_CHANNEL_ID"),
            volleyball=env.get("VOLLEYBALL_CHANNEL_ID"),
            baseball=env.get("BASEBALL_CHANNEL_ID"),
            default=env.get("DEFAULT_SPORT_CHANNEL_ID"),
        )


settings = Config()
