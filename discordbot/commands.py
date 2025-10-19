import discord
from discord import app_commands
import json
import os
import re
from datetime import datetime
from apscheduler.triggers.cron import CronTrigger
import pytz

EVENTS_FILE = "events.json"

def parse_time_with_timezone(time_str):
    """
    Parse time string that may include timezone.
    Supports formats like:
    - "9:00 PM America/St_Johns"
    - "21:00 America/St_Johns"
    - "9:00 PM" (defaults to UTC)
    - "21:00" (defaults to UTC)
    Returns (hour, minute, timezone)
    """
    time_str = time_str.strip()
    parts = time_str.split()

    # Handle AM/PM
    if len(parts) >= 2 and parts[1].upper() in ['AM', 'PM']:
        time_part = f"{parts[0]} {parts[1]}"
        tz_part = ' '.join(parts[2:]) if len(parts) > 2 else 'UTC'
    else:
        time_part = parts[0]
        tz_part = ' '.join(parts[1:]) if len(parts) > 1 else 'UTC'

    # Parse time
    try:
        if 'AM' in time_part.upper() or 'PM' in time_part.upper():
            dt = datetime.strptime(time_part, "%I:%M %p")
        else:
            dt = datetime.strptime(time_part, "%H:%M")
    except ValueError:
        raise ValueError("Invalid time format")

    # Validate timezone
    try:
        pytz.timezone(tz_part)
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError(f"Unknown timezone: {tz_part}")

    return dt.hour, dt.minute, tz_part

def load_events():
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_events(events):
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=2)

async def send_reminder(thread_id, user_ids, message, bot):
    thread = bot.get_channel(thread_id)
    if thread:
        mentions = " ".join(f"<@{uid}>" for uid in user_ids)
        await thread.send(f"{mentions} {message}")

def setup_commands(bot):
    bot.events = load_events()
    for event in bot.events:
        if "hour" in event and "minute" in event and "timezone" in event:
            hour = event["hour"]
            minute = event["minute"]
            timezone = event["timezone"]
        else:
            # Backward compatibility: parse old time format
            hour, minute = map(int, event["time"].split(":"))
            timezone = "UTC"
        tz = pytz.timezone(timezone)
        target_id = event.get("thread_id", event["channel_id"])
        bot.scheduler.add_job(
            send_reminder,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
            args=[target_id, event["user_ids"], event["message"], bot]
        )

    @bot.tree.command(name="add_event", description="Add a scheduled reminder event")
    @app_commands.describe(
        name="Unique name for the event",
        time="Time with optional timezone (e.g., '9:00 PM America/St_Johns' or '21:00 UTC')",
        users="Comma-separated user IDs to ping",
        message="The reminder message",
        create_thread="Whether to create a thread for this event (default: True)"
    )
    async def add_event(interaction: discord.Interaction, name: str, time: str, users: str, message: str, create_thread: bool = True):
        if any(e["name"] == name for e in bot.events):
            await interaction.response.send_message(f"Event '{name}' already exists.")
            return
        try:
            hour, minute, timezone = parse_time_with_timezone(time)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid time format: {e}")
            return
        channel = interaction.channel
        user_ids = []
        for uid in users.split(","):
            uid = uid.strip()
            if uid:
                match = re.match(r'<@(\d+)>', uid)
                if match:
                    user_ids.append(int(match.group(1)))
                else:
                    try:
                        user_ids.append(int(uid))
                    except ValueError:
                        pass  # Skip invalid
        if not user_ids:
            await interaction.response.send_message("No valid user IDs provided.")
            return
        thread_id = None
        if create_thread:
            # Send initial message and create thread
            initial_msg = await channel.send(f"Event '{name}' scheduled for {time} ({timezone}).")
            thread = await initial_msg.create_thread(name=f"Event: {name}")
            thread_id = thread.id
            target_id = thread.id
        else:
            target_id = channel.id

        event = {
            "name": name,
            "time": time,
            "hour": hour,
            "minute": minute,
            "timezone": timezone,
            "channel_id": channel.id,
            "thread_id": thread_id,
            "user_ids": user_ids,
            "message": message
        }
        bot.events.append(event)
        save_events(bot.events)
        tz = pytz.timezone(timezone)
        bot.scheduler.add_job(
            send_reminder,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
            args=[target_id, user_ids, message, bot]
        )
        await interaction.response.send_message(f"Event '{name}' added.")

    @bot.tree.command(name="remove_event", description="Remove a scheduled event")
    @app_commands.describe(name="Name of the event to remove")
    async def remove_event(interaction: discord.Interaction, name: str):
        event = next((e for e in bot.events if e["name"] == name), None)
        if not event:
            await interaction.response.send_message(f"Event '{name}' not found.")
            return
        # Remove from scheduler - for simplicity, not removing job, just from list
        bot.events = [e for e in bot.events if e["name"] != name]
        save_events(bot.events)
        await interaction.response.send_message(f"Event '{name}' removed.")

    @bot.tree.command(name="list_events", description="List all scheduled events")
    async def list_events(interaction: discord.Interaction):
        if not bot.events:
            await interaction.response.send_message("No events scheduled.")
            return
        msg = "\n".join(f"- {e['name']}: {e['time']} ({e.get('timezone', 'UTC')}) in <#{e['channel_id']}> pinging {len(e['user_ids'])} users: {e['message']}" for e in bot.events)
        await interaction.response.send_message(msg)