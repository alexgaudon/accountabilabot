import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discordbot.commands import setup_commands
from discordbot.challenges import setup_challenge_commands

class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.scheduler = AsyncIOScheduler()
        self.events = []

    async def on_ready(self):
        print(f'Logged in as {self.user}')
        self.scheduler.start()
        setup_commands(self)
        setup_challenge_commands(self)
        await self.tree.sync()
