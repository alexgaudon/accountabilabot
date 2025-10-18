from abc import ABC, abstractmethod
from discord import Message
import discord


class Command(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def execute(self, message: Message) -> None:
        pass

    @abstractmethod
    def matches(self, message: Message) -> bool:
        pass


class PingCommand(Command):
    def __init__(self):
        super().__init__("ping")

    def matches(self, message: Message) -> bool:
        return message.content.lower().strip() == "!ping"

    async def execute(self, message: Message) -> None:
        await message.channel.send("Pong!")


class EchoCommand(Command):
    def __init__(self):
        super().__init__("echo")

    def matches(self, message: Message) -> bool:
        return message.content.lower().startswith("!echo ")

    async def execute(self, message: Message) -> None:
        content = message.content[6:].strip()  # Remove "!echo "
        if content:
            await message.channel.send(content)
        else:
            await message.channel.send("Usage: !echo <message>")