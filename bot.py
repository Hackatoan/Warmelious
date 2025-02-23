import discord
from discord.ext import commands
from discord import app_commands
import requests
import json
import os
import asyncio

# --- Load & Save TTS Channel Settings ---

SERVER_SETTINGS_FILE = "server_settings.json"

def load_settings():
    """Load server settings from a file."""
    global server_settings
    if os.path.exists(SERVER_SETTINGS_FILE):
        with open(SERVER_SETTINGS_FILE, "r") as f:
            try:
                server_settings = json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Error loading server settings! Resetting file.")
                server_settings = {}
                save_settings()
    else:
        server_settings = {}
    print(f"✅ Loaded server settings: {server_settings}")  # Debugging


def save_settings():
    """Save server settings to a file."""
    with open(SERVER_SETTINGS_FILE, "w") as f:
        json.dump(server_settings, f, indent=4)

# Load settings on bot startup
load_settings()

# Load configuration
with open("config.json", "r") as config_file:
    config = json.load(config_file)

TOKEN = config["TOKEN"]
ELEVENLABS_API_KEY = config["ELEVENLABS_API_KEY"]

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="w!", intents=intents)
tree = bot.tree  # Slash command handler

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Default voice (Rachel)
SERVER_SETTINGS_FILE = "server_settings.json"
server_settings = {}

# --- Remove Default Help Command to Avoid Conflict ---
bot.remove_command("help")

# --- Sync Slash Commands on Startup ---
@bot.event
async def on_ready():
    """Ensure settings are loaded and sync slash commands."""
    load_settings()  # Load settings on bot startup

    try:
        await bot.tree.sync()
        print(f"✅ Slash commands synced! Logged in as {bot.user.name}")
    except Exception as e:
        print(f"⚠️ Error syncing slash commands: {e}")

    # Debugging: Print loaded TTS channels
    for server_id, settings in server_settings.items():
        if "tts_channel_id" in settings:
            print(f"📢 TTS channel for server {server_id}: {settings['tts_channel_id']}")


# --- Fetch Available Voices ---
def get_available_voices():
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        voices = response.json().get("voices", [])
        return {voice["name"]: voice["voice_id"] for voice in voices}
    else:
        print("Error fetching voices:", response.json())
        return {}

# --- Get & Save User Voice ---
def get_user_voice(user_id):
    return config.get("user_voices", {}).get(str(user_id), DEFAULT_VOICE_ID)

def save_user_voice(user_id, voice_id):
    config.setdefault("user_voices", {})[str(user_id)] = voice_id
    with open("config.json", "w") as config_file:
        json.dump(config, config_file, indent=4)

# --- ElevenLabs TTS ---
def text_to_speech_elevenlabs(user_id, text):
    """Converts text to speech using ElevenLabs API."""
    voice_id = get_user_voice(user_id)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        with open("temp.mp3", "wb") as f:
            f.write(response.content)
        return "temp.mp3"
    else:
        print("Error:", response.json())
        return None

# --- Play TTS ---
async def play_tts(voice_channel, user_id, text):
    """Plays the generated TTS in a voice channel."""
    if voice_channel is None:
        return

    file_path = text_to_speech_elevenlabs(user_id, text)
    if not file_path:
        return

    try:
        voice_client = discord.utils.get(bot.voice_clients, guild=voice_channel.guild)
        if voice_client is None or not voice_client.is_connected():
            voice_client = await voice_channel.connect()

        source = discord.FFmpegOpusAudio(file_path)
        voice_client.play(source)

        while voice_client.is_playing():
            await asyncio.sleep(1)

    except Exception as e:
        print(f"Error playing TTS: {e}")
        if voice_channel.guild.voice_client:
            await voice_channel.guild.voice_client.disconnect()

    finally:
        os.remove("temp.mp3")

# --- Slash Commands ---

@tree.command(name="listvoices", description="Show available ElevenLabs voices")
async def slash_listvoices(interaction: discord.Interaction):
    """List all available voices (slash command)."""
    voices = get_available_voices()
    if voices:
        voice_list = "\n".join([f"**{name}** - `{voice_id}`" for name, voice_id in voices.items()])
        embed = discord.Embed(title="🎙️ Available Voices", description=voice_list, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("Error fetching voices. Please try again later.", ephemeral=True)

@tree.command(name="setvoice", description="Set your ElevenLabs voice")
@app_commands.describe(voice_name_or_id="The name or ID of the voice to set")
async def slash_setvoice(interaction: discord.Interaction, voice_name_or_id: str):
    """Set the user's voice (slash command)."""
    voices = get_available_voices()

    if voice_name_or_id in voices:
        voice_id = voices[voice_name_or_id]
    elif voice_name_or_id in voices.values():
        voice_id = voice_name_or_id
    else:
        await interaction.response.send_message("Invalid voice name or ID. Use `/listvoices` to see available options.", ephemeral=True)
        return

    save_user_voice(interaction.user.id, voice_id)
    await interaction.response.send_message(f"✅ Your voice has been set to `{voice_name_or_id}`.", ephemeral=True)

@tree.command(name="myvoice", description="Show your currently selected ElevenLabs voice")
async def slash_myvoice(interaction: discord.Interaction):
    """Show the user's currently selected voice (slash command)."""
    voice_id = get_user_voice(interaction.user.id)
    voices = get_available_voices()
    voice_name = next((name for name, vid in voices.items() if vid == voice_id), "Unknown")

    embed = discord.Embed(title="🎙️ Your Selected Voice", description=f"**Name:** `{voice_name}`\n**ID:** `{voice_id}`", color=discord.Color.purple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="help", description="Show available bot commands")
async def slash_help(interaction: discord.Interaction):
    """Slash version of the help command."""
    embed = discord.Embed(title="📢 TTS Bot Commands", description="Here's a list of my commands:", color=discord.Color.green())

    embed.add_field(name="🔊 Voice Commands", value=
        "**`/tts <message>`** - Speak a message in voice chat.\n"
        "**`/settts #channel`** - Set a TTS text channel.", inline=False)

    embed.add_field(name="🗣️ Voice Selection", value=
        "**`/listvoices`** - Show available voices.\n"
        "**`/setvoice <name>`** - Set your ElevenLabs voice.\n"
        "**`/myvoice`** - Show your selected voice.", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

def save_settings():
    """Saves server settings to a file."""
    with open(SERVER_SETTINGS_FILE, "w") as f:
        json.dump(server_settings, f, indent=4)



# --- Prefix Commands ---
@bot.command(name="help")
async def help_command(ctx):
    """Displays all available bot commands."""
    embed = discord.Embed(title="📢 TTS Bot Commands", description="Here's what I can do:", color=discord.Color.blue())

    embed.add_field(name="🔊 Voice Commands", value=
        "**`w!tts <message>`** - Speak a message in voice chat.\n"
        "**`w!settts #channel`** - Set a TTS text channel.", inline=False)

    embed.add_field(name="🗣️ Voice Selection", value=
        "**`w!listvoices`** - Show available voices.\n"
        "**`w!setvoice <name>`** - Set your ElevenLabs voice.\n"
        "**`w!myvoice`** - Show your selected voice.", inline=False)

    embed.set_footer(text="Use /help for slash command help.")

    await ctx.send(embed=embed)

@bot.command(name="tts")
async def tts(ctx, *, message: str):
    """Manually speak a message in voice chat."""
    if ctx.author.voice and ctx.author.voice.channel:
        await play_tts(ctx.author.voice.channel, ctx.author.id, message)
        await ctx.send("Playing TTS...", delete_after=5)
    else:
        await ctx.send("You must be in a voice channel to use this command.")

@bot.command(name="listvoices")
async def list_voices(ctx):
    """List all available voices."""
    voices = get_available_voices()
    if voices:
        voice_list = "\n".join([f"**{name}** - `{voice_id}`" for name, voice_id in voices.items()])
        embed = discord.Embed(title="🎙️ Available Voices", description=voice_list, color=discord.Color.blue())
        await ctx.send(embed=embed)
    else:
        await ctx.send("Error fetching voices. Please try again later.")

@bot.command(name="setvoice")
async def set_voice(ctx, voice_name_or_id: str):
    """Set the user's voice."""
    voices = get_available_voices()

    if voice_name_or_id in voices:
        voice_id = voices[voice_name_or_id]
    elif voice_name_or_id in voices.values():
        voice_id = voice_name_or_id
    else:
        await ctx.send("Invalid voice name or ID. Use `w!listvoices` to see available options.")
        return

    save_user_voice(ctx.author.id, voice_id)
    await ctx.send(f"✅ Your voice has been set to `{voice_name_or_id}`.")

@bot.command(name="myvoice")
async def my_voice(ctx):
    """Show the user's currently selected voice."""
    voice_id = get_user_voice(ctx.author.id)
    voices = get_available_voices()
    voice_name = next((name for name, vid in voices.items() if vid == voice_id), "Unknown")

    embed = discord.Embed(title="🎙️ Your Selected Voice", description=f"**Name:** `{voice_name}`\n**ID:** `{voice_id}`", color=discord.Color.purple())
    await ctx.send(embed=embed)


@bot.command(name="settts")
async def set_tts(ctx, channel: discord.TextChannel):
    """Set the TTS text channel (Prefix Command)."""
    server_id = str(ctx.guild.id)
    server_settings.setdefault(server_id, {})["tts_channel_id"] = channel.id

    save_settings()
    await ctx.send(f"✅ TTS messages will now be spoken from {channel.mention} (saved on restart).")

@tree.command(name="settts", description="Set a TTS text channel")
async def slash_settts(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set the TTS text channel (Slash Command)."""
    server_id = str(interaction.guild.id)
    server_settings.setdefault(server_id, {})["tts_channel_id"] = channel.id

    save_settings()
    await interaction.response.send_message(f"✅ TTS messages will now be spoken from {channel.mention} (saved on restart).", ephemeral=True)



# --- Ensure Prefix Commands & Auto-TTS Work ---
@bot.event
async def on_message(message):
    """Processes commands and handles Auto-TTS."""
    if message.author == bot.user:
        return  

    await bot.process_commands(message)  # Ensure prefix commands (`w!`) work

    server_id = str(message.guild.id)

    # Debugging: Check if the bot is recognizing messages
    print(f"📩 Message received in {message.channel.id}: {message.content}")

    # Ensure settings are loaded
    if server_id not in server_settings:
        print(f"⚠️ Server {server_id} settings not loaded!")
        load_settings()

    # Load the saved TTS channel from settings
    if "tts_channel_id" in server_settings.get(server_id, {}):
        tts_channel_id = server_settings[server_id]["tts_channel_id"]

        # Debugging: Print detected channel
        print(f"🔎 Checking if {message.channel.id} matches saved TTS channel {tts_channel_id}")

        # If the message is sent in the saved TTS channel, trigger Auto-TTS
        if message.channel.id == tts_channel_id:
            if message.author.voice and message.author.voice.channel:
                print("🎙️ Auto-TTS Triggered!")
                await play_tts(message.author.voice.channel, message.author.id, message.content)
                return  # Prevent further processing

    # Auto-TTS for messages sent in voice chat text channels
    if isinstance(message.channel, discord.VoiceChannel):
        if message.author.voice and message.author.voice.channel:
            print("🎙️ Auto-TTS Triggered for Voice Channel!")
            await play_tts(message.author.voice.channel, message.author.id, message.content)



bot.run(TOKEN)
