# DiscordBot Boilerplate

A simple Discord bot boilerplate built with discord.py.

## Features

- Command handler system for easy command registration
- Example commands: `!ping` and `!echo`
- Configurable via environment variables

## Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Create a `.env` file with your Discord bot token:
   ```
   discord_token=your_bot_token_here
   ```

3. Run the bot:
   ```bash
   uv run python -m discordbot
   ```

## Adding Commands

Create new command classes in `discordbot/commands.py` that inherit from `Command` and implement `matches()` and `execute()` methods.
