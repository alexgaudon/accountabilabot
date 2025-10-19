import discord
from discord import app_commands, ui
import json
import os
import re
from typing import Optional
from datetime import datetime
from apscheduler.triggers.cron import CronTrigger
import pytz

CHALLENGES_FILE = "challenges.json"

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

def load_challenges():
    if os.path.exists(CHALLENGES_FILE):
        with open(CHALLENGES_FILE, "r") as f:
            return json.load(f)
    return []

def save_challenges(challenges):
    with open(CHALLENGES_FILE, "w") as f:
        json.dump(challenges, f, indent=2)

async def send_challenge_reminder(thread_id, user_ids, message, bot):
    thread = bot.get_channel(thread_id)
    if thread:
        mentions = " ".join(f"<@{uid}>" for uid in user_ids)
        await thread.send(f"{mentions} {message}")

def setup_challenge_scheduler(bot):
    bot.challenges = load_challenges()
    for challenge in bot.challenges:
        if "hour" in challenge and "minute" in challenge and "timezone" in challenge:
            hour = challenge["hour"]
            minute = challenge["minute"]
            timezone = challenge["timezone"]
        else:
            # Backward compatibility: parse old time format
            hour, minute = map(int, challenge["time"].split(":"))
            timezone = "UTC"
        tz = pytz.timezone(timezone)
        if challenge["frequency"] == "daily":
            trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)
        elif challenge["frequency"] == "weekly":
            day = challenge.get("day", "mon")  # default to monday if not set
            trigger = CronTrigger(day_of_week=day[:3].lower(), hour=hour, minute=minute, timezone=tz)
        else:
            continue  # invalid frequency
        target_id = challenge.get("thread_id", challenge["channel_id"])
        job = bot.scheduler.add_job(
            send_challenge_reminder,
            trigger=trigger,
            args=[target_id, challenge["members"], challenge["message"], bot]
        )
        challenge["job_id"] = job.id

async def challenge_name_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for challenge names"""
    return [
        app_commands.Choice(name=challenge["name"], value=challenge["name"])
        for challenge in interaction.client.challenges
        if current.lower() in challenge["name"].lower()
    ]

class EditChallengeModal(ui.Modal):
    def __init__(self, challenge, bot):
        super().__init__(title="Edit Challenge")
        self.challenge = challenge
        self.bot = bot

        self.name_input = ui.TextInput(label="Name", default=challenge["name"])
        self.description_input = ui.TextInput(label="Description", default=challenge["description"], style=discord.TextStyle.paragraph)
        time_freq_default = f"{challenge['time']} {challenge['frequency']}"
        if challenge.get("day"):
            time_freq_default += f" {challenge['day']}"
        self.time_freq_input = ui.TextInput(label="Time and Frequency", placeholder="e.g., '10:00 daily' or '9:00 PM America/St_Johns weekly monday'", default=time_freq_default)
        self.message_input = ui.TextInput(label="Message", default=challenge["message"], style=discord.TextStyle.paragraph)

        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.time_freq_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate
        name = self.name_input.value.strip()
        description = self.description_input.value.strip()
        time_freq = self.time_freq_input.value.strip()
        message = self.message_input.value.strip()

        if not name or not description or not time_freq or not message:
            await interaction.response.send_message("All fields are required.")
            return

        # Parse time_freq: [time] frequency [day]
        parts = time_freq.split()
        if len(parts) < 2:
            await interaction.response.send_message("Time and Frequency must be in format 'HH:MM daily' or '9:00 PM America/St_Johns weekly monday'.")
            return

        # Find frequency (daily or weekly)
        frequency_idx = -1
        for i, part in enumerate(parts):
            if part.lower() in ["daily", "weekly"]:
                frequency_idx = i
                break
        if frequency_idx == -1:
            await interaction.response.send_message("Must include 'daily' or 'weekly' frequency.")
            return

        time_str = ' '.join(parts[:frequency_idx])
        frequency = parts[frequency_idx].lower()
        day = parts[frequency_idx + 1].lower() if frequency_idx + 1 < len(parts) else None

        # Check name unique if changed
        if name != self.challenge["name"] and any(c["name"] == name for c in self.bot.challenges):
            await interaction.response.send_message(f"Challenge '{name}' already exists.")
            return

        # Validate time
        try:
            hour, minute, timezone = parse_time_with_timezone(time_str)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid time format: {e}")
            return

        # Validate frequency
        if frequency not in ["daily", "weekly"]:
            await interaction.response.send_message("Frequency must be 'daily' or 'weekly'.")
            return

        if frequency == "weekly" and not day:
            await interaction.response.send_message("Day must be specified for weekly challenges.")
            return

        if frequency == "weekly":
            valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            if day not in valid_days:
                await interaction.response.send_message("Invalid day. Use full day name like 'monday'.")
                return

        # Parse channel
        channel_id = interaction.channel.id  # use the channel where the edit command was run

        # Update challenge
        old_frequency = self.challenge["frequency"]
        old_time = self.challenge["time"]
        old_day = self.challenge.get("day")

        self.challenge["name"] = name
        self.challenge["description"] = description
        self.challenge["time"] = time_str  # Store the original time string
        self.challenge["hour"] = hour
        self.challenge["minute"] = minute
        self.challenge["timezone"] = timezone
        self.challenge["frequency"] = frequency
        self.challenge["day"] = day
        self.challenge["channel_id"] = channel_id
        self.challenge["message"] = message

        save_challenges(self.bot.challenges)

        # Update scheduler if needed
        if (frequency != old_frequency or time_str != old_time or (frequency == "weekly" and day != old_day)):
            # Remove old job
            if "job_id" in self.challenge:
                self.bot.scheduler.remove_job(self.challenge["job_id"])
            # Add new job
            tz = pytz.timezone(timezone)
            if frequency == "daily":
                trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)
            elif frequency == "weekly":
                trigger = CronTrigger(day_of_week=day[:3], hour=hour, minute=minute, timezone=tz)
            job = self.bot.scheduler.add_job(
                send_challenge_reminder,
                trigger=trigger,
                args=[channel_id, self.challenge["members"], message, self.bot]
            )
            self.challenge["job_id"] = job.id

        await interaction.response.send_message(f"Challenge '{name}' updated.")

def setup_challenge_commands(bot):
    setup_challenge_scheduler(bot)

    @bot.tree.command(name="create_challenge", description="Create a new challenge")
    @app_commands.describe(
        name="Unique name for the challenge",
        description="Description of the challenge",
        time="Time with optional timezone (e.g., '9:00 PM America/St_Johns' or '21:00 UTC')",
        frequency="Frequency: daily or weekly",
        day="Day of week for weekly challenges (e.g., monday, tuesday)",
        message="The reminder message"
    )
    async def create_challenge(interaction: discord.Interaction, name: str, description: str, time: str, frequency: str, day: Optional[str] = None, message: str = "Time for your challenge!"):
        if any(c["name"] == name for c in bot.challenges):
            await interaction.response.send_message(f"Challenge '{name}' already exists.")
            return
        try:
            hour, minute, timezone = parse_time_with_timezone(time)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid time format: {e}")
            return
        if frequency not in ["daily", "weekly"]:
            await interaction.response.send_message("Frequency must be 'daily' or 'weekly'.")
            return
        if frequency == "weekly":
            if not day:
                await interaction.response.send_message("Day must be specified for weekly challenges.")
                return
            valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            if day.lower() not in valid_days:
                await interaction.response.send_message("Invalid day. Use full day name like 'monday'.")
                return
        channel_id = interaction.channel.id
        thread_id = interaction.channel.id if isinstance(interaction.channel, discord.Thread) else None
        target_id = interaction.channel.id

        challenge = {
            "name": name,
            "description": description,
            "creator": interaction.user.id,
            "members": [interaction.user.id],  # creator is initial member
            "frequency": frequency,
            "time": time,
            "hour": hour,
            "minute": minute,
            "timezone": timezone,
            "day": day.lower() if day else None,
            "channel_id": channel_id,
            "thread_id": thread_id,
            "message": message
        }
        bot.challenges.append(challenge)
        save_challenges(bot.challenges)
        # Add to scheduler
        tz = pytz.timezone(timezone)
        if frequency == "daily":
            trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)
        elif frequency == "weekly":
            trigger = CronTrigger(day_of_week=day[:3].lower(), hour=hour, minute=minute, timezone=tz)
        bot.scheduler.add_job(
            send_challenge_reminder,
            trigger=trigger,
            args=[target_id, challenge["members"], message, bot]
        )
        await interaction.response.send_message(f"Challenge '{name}' created and you have joined it.")

    @bot.tree.command(name="join_challenge", description="Join an existing challenge")
    @app_commands.autocomplete(name=challenge_name_autocomplete)
    @app_commands.describe(name="Name of the challenge to join")
    async def join_challenge(interaction: discord.Interaction, name: str):
        challenge = next((c for c in bot.challenges if c["name"] == name), None)
        if not challenge:
            await interaction.response.send_message(f"Challenge '{name}' not found.")
            return
        if interaction.user.id in challenge["members"]:
            await interaction.response.send_message("You are already in this challenge.")
            return
        challenge["members"].append(interaction.user.id)
        save_challenges(bot.challenges)
        await interaction.response.send_message(f"You have joined the challenge '{name}'.")

    @bot.tree.command(name="leave_challenge", description="Leave a challenge")
    @app_commands.autocomplete(name=challenge_name_autocomplete)
    @app_commands.describe(name="Name of the challenge to leave")
    async def leave_challenge(interaction: discord.Interaction, name: str):
        challenge = next((c for c in bot.challenges if c["name"] == name), None)
        if not challenge:
            await interaction.response.send_message(f"Challenge '{name}' not found.")
            return
        if interaction.user.id not in challenge["members"]:
            await interaction.response.send_message("You are not in this challenge.")
            return
        if interaction.user.id == challenge["creator"] and len(challenge["members"]) == 1:
            await interaction.response.send_message("You cannot leave as the creator and only member. Remove the challenge instead.")
            return
        challenge["members"].remove(interaction.user.id)
        save_challenges(bot.challenges)
        await interaction.response.send_message(f"You have left the challenge '{name}'.")

    @bot.tree.command(name="list_challenges", description="List all challenges")
    async def list_challenges(interaction: discord.Interaction):
        if not bot.challenges:
            await interaction.response.send_message("No challenges available.")
            return
        msg = "\n".join(f"- **{c['name']}**: {c['description']} ({c['frequency']} at {c['time']} ({c.get('timezone', 'UTC')})) - {len(c['members'])} members" for c in bot.challenges)
        await interaction.response.send_message(msg)

    @bot.tree.command(name="invite_challenge", description="Invite users to join a challenge")
    @app_commands.autocomplete(name=challenge_name_autocomplete)
    @app_commands.describe(
        name="Name of the challenge",
        users="Users to invite (mention them)"
    )
    async def invite_challenge(interaction: discord.Interaction, name: str, users: str):
        challenge = next((c for c in bot.challenges if c["name"] == name), None)
        if not challenge:
            await interaction.response.send_message(f"Challenge '{name}' not found.")
            return
        if interaction.user.id not in challenge["members"]:
            await interaction.response.send_message("You must be a member of the challenge to invite others.")
            return
        invited_users = []
        for uid in users.split():
            uid = uid.strip()
            if uid:
                match = re.match(r'<@(\d+)>', uid)
                if match:
                    user_id = int(match.group(1))
                    if user_id not in challenge["members"]:
                        invited_users.append(f"<@{user_id}>")
        if not invited_users:
            await interaction.response.send_message("No valid users to invite (they may already be in the challenge).")
            return
        invite_msg = f"{interaction.user.mention} invites you to join the challenge **{name}**: {challenge['description']}\nUse `/join_challenge name:{name}` to join!"
        await interaction.response.send_message(f"{', '.join(invited_users)} {invite_msg}")

    @bot.tree.command(name="remove_challenge", description="Remove a challenge (creator only)")
    @app_commands.autocomplete(name=challenge_name_autocomplete)
    @app_commands.describe(name="Name of the challenge to remove")
    async def remove_challenge(interaction: discord.Interaction, name: str):
        challenge = next((c for c in bot.challenges if c["name"] == name), None)
        if not challenge:
            await interaction.response.send_message(f"Challenge '{name}' not found.")
            return
        if interaction.user.id != challenge["creator"]:
            await interaction.response.send_message("Only the creator can remove this challenge.")
            return
        bot.challenges = [c for c in bot.challenges if c["name"] != name]
        save_challenges(bot.challenges)
        await interaction.response.send_message(f"Challenge '{name}' removed.")

    @bot.tree.command(name="edit_challenge", description="Edit a challenge (creator only)")
    @app_commands.autocomplete(name=challenge_name_autocomplete)
    @app_commands.describe(name="Name of the challenge to edit")
    async def edit_challenge(interaction: discord.Interaction, name: str):
        challenge = next((c for c in bot.challenges if c["name"] == name), None)
        if not challenge:
            await interaction.response.send_message(f"Challenge '{name}' not found.")
            return
        if interaction.user.id != challenge["creator"]:
            await interaction.response.send_message("Only the creator can edit this challenge.")
            return
        modal = EditChallengeModal(challenge, bot)
        await interaction.response.send_modal(modal)