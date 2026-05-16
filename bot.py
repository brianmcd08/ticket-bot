import os

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

guild_str = os.getenv("GUILD_ID")
assert guild_str, "GUILD_ID not found in .env"
guild_id = int(guild_str)
guild = discord.Object(id=guild_id)


@tree.command(name="have", description="you have ticket(s)", guild=guild)
async def have(interaction: discord.Interaction):
    await interaction.response.send_message("have received!")


@tree.command(name="want", description="you want ticket(s)", guild=guild)
async def want(interaction: discord.Interaction):
    await interaction.response.send_message("want received!")


@tree.command(name="close", description="close open tickets", guild=guild)
async def close(interaction: discord.Interaction):
    await interaction.response.send_message("close received!")


@client.event
async def on_ready():
    print(f"Successfully connected! Logged in as {client.user}")
    channel_str = os.getenv("CHANNEL_ID")
    assert channel_str, "Channel not found"

    channel_id = int(channel_str)
    channel = client.get_channel(channel_id)

    if channel:
        print("Channel exists!")
    else:
        print("Channel doesn't exist")

    synced = await tree.sync(guild=guild)
    print("Command tree synced!")

    print(f"Commands in tree: {[cmd.name for cmd in tree.get_commands()]}")
    print(f"Synced {len(synced)} commands: {[cmd.name for cmd in synced]}")


# run
token = os.getenv("DISCORD_TOKEN")
assert token, "DISCORD_TOKEN not found in .env"
client.run(token=token)
