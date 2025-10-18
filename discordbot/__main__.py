import logging
from .bot import DiscordBot
from .config import config


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    if not config.discord_token:
        raise ValueError("DISCORD_TOKEN environment variable is required. Create a .env file with discord_token = 'your_token_here'")
    bot = DiscordBot()
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()