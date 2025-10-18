import discord
from discordbot.command_handler import CommandHandler
from discordbot.commands import PingCommand, EchoCommand

class DiscordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self.command_handler = CommandHandler()
        # Register example commands
        self.command_handler.register(PingCommand())
        self.command_handler.register(EchoCommand())

    async def on_ready(self):
        print(f'Logged in as {self.user}')

    async def on_message(self, message):
        if message.author.bot or message.author == self.user:
            return

        await self.command_handler.execute(message)
