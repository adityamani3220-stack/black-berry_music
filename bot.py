import os
import asyncio
import logging
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands

from music import MusicManager

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
music = MusicManager(bot)

# Per-guild authorized users and allowed command channels.
authorized = {}       # guild_id -> set(user_id)
allowed_channels = {} # guild_id -> set(channel_id)


def is_authorized(guild_id: int, user_id: int) -> bool:
    return user_id in authorized.get(guild_id, set())


def is_admin(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild and isinstance(interaction.user, discord.Member)
                and interaction.user.guild_permissions.administrator)


async def require_admin(interaction: discord.Interaction) -> bool:
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return False
    return True


async def require_music_access(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
        return False
    chans = allowed_channels.get(interaction.guild.id)
    if chans and interaction.channel_id not in chans and not is_admin(interaction):
        await interaction.response.send_message("❌ This channel is not added with `/channeladd`.", ephemeral=True)
        return False
    if not is_admin(interaction) and authorized.get(interaction.guild.id):
        if not is_authorized(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("❌ You are not authorized. Ask an admin to use `/auth @member`.", ephemeral=True)
            return False
    return True


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        logging.info("Logged in as %s | synced %d slash commands", bot.user, len(synced))
    except Exception:
        logging.exception("Slash command sync failed")


# ---------- MUSIC ----------
@bot.tree.command(name="play", description="Play a YouTube URL/search or Spotify track/playlist URL.")
@app_commands.describe(query="Song name, YouTube URL, or Spotify URL")
async def play(interaction: discord.Interaction, query: str):
    if not await require_music_access(interaction): return
    await interaction.response.defer()
    try:
        msg = await music.play(interaction.guild, interaction.user, query)
        await interaction.followup.send(msg)
    except Exception as e:
        logging.exception("play failed")
        await interaction.followup.send(f"❌ {e}")


@bot.tree.command(name="vplay", description="Voice play alias: join your voice channel and play a song.")
@app_commands.describe(query="Song name or URL")
async def vplay(interaction: discord.Interaction, query: str):
    if not await require_music_access(interaction): return
    await interaction.response.defer()
    try:
        msg = await music.play(interaction.guild, interaction.user, query)
        await interaction.followup.send(msg)
    except Exception as e:
        logging.exception("vplay failed")
        await interaction.followup.send(f"❌ {e}")


@bot.tree.command(name="start", description="Start/resume the current music.")
async def start(interaction: discord.Interaction):
    if not await require_music_access(interaction): return
    await interaction.response.send_message(music.resume(interaction.guild.id))


@bot.tree.command(name="pause", description="Pause the current music.")
async def pause(interaction: discord.Interaction):
    if not await require_music_access(interaction): return
    await interaction.response.send_message(music.pause(interaction.guild.id))


@bot.tree.command(name="stop", description="Stop music and clear the queue.")
async def stop(interaction: discord.Interaction):
    if not await require_music_access(interaction): return
    await interaction.response.send_message(await music.stop(interaction.guild.id))


@bot.tree.command(name="skip", description="Skip the current song.")
async def skip(interaction: discord.Interaction):
    if not await require_music_access(interaction): return
    await interaction.response.send_message(await music.skip(interaction.guild.id))


@bot.tree.command(name="queue", description="Show the current music queue.")
async def queue(interaction: discord.Interaction):
    if not await require_music_access(interaction): return
    await interaction.response.send_message(music.queue_text(interaction.guild.id))


@bot.tree.command(name="shuffle", description="Shuffle the waiting queue.")
async def shuffle(interaction: discord.Interaction):
    if not await require_music_access(interaction): return
    await interaction.response.send_message(music.shuffle(interaction.guild.id))


@bot.tree.command(name="speed", description="Change playback speed from 0.5x to 2.0x.")
@app_commands.describe(value="Playback speed, e.g. 1.25")
async def speed(interaction: discord.Interaction, value: app_commands.Range[float, 0.5, 2.0]):
    if not await require_music_access(interaction): return
    await interaction.response.defer()
    await interaction.followup.send(await music.speed(interaction.guild.id, float(value)))


@bot.tree.command(name="seek", description="Jump forward in the current song by N seconds.")
@app_commands.describe(seconds="Seconds to move forward")
async def seek(interaction: discord.Interaction, seconds: app_commands.Range[int, 1, 3600]):
    if not await require_music_access(interaction): return
    await interaction.response.defer()
    await interaction.followup.send(await music.seek(interaction.guild.id, int(seconds)))


@bot.tree.command(name="seekback", description="Jump backward in the current song by N seconds.")
@app_commands.describe(seconds="Seconds to move backward")
async def seekback(interaction: discord.Interaction, seconds: app_commands.Range[int, 1, 3600]):
    if not await require_music_access(interaction): return
    await interaction.response.defer()
    await interaction.followup.send(await music.seek(interaction.guild.id, -int(seconds)))


@bot.tree.command(name="nowplaying", description="Show the current song.")
async def nowplaying(interaction: discord.Interaction):
    if not await require_music_access(interaction): return
    await interaction.response.send_message(music.nowplaying(interaction.guild.id))


@bot.command(name="alltag")
@commands.has_guild_permissions(manage_guild=True)
async def prefix_alltag(ctx: commands.Context):
    if not ctx.guild:
        return
    members = [m for m in ctx.guild.members if not m.bot]
    chunks, current = [], ""
    for member in members:
        mention = f"{member.mention} "
        if len(current) + len(mention) > 1900:
            if current:
                chunks.append(current)
            current = mention
        else:
            current += mention
    if current:
        chunks.append(current)

    await ctx.send(f"📢 Tagging **{len(members)}** members...")
    allowed = discord.AllowedMentions(users=True, everyone=False, roles=False, replied_user=False)
    for chunk in chunks:
        await ctx.send(chunk, allowed_mentions=allowed)
        await asyncio.sleep(0.35)


@prefix_alltag.error
async def prefix_alltag_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Manage Server permission required.")


# ---------- SERVER / UTILITY ----------
@bot.tree.command(name="ping", description="Show bot latency.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! `{round(bot.latency * 1000)} ms`")


@bot.tree.command(name="id", description="Show a member's user ID.")
@app_commands.describe(member="Member to inspect")
async def id_cmd(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    await interaction.response.send_message(f"🆔 {member.mention} → `{member.id}`")


async def _tag_all_members(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("❌ Server only.", ephemeral=True)

    if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message(
            "❌ Manage Server permission required.", ephemeral=True
        )

    members = [m for m in interaction.guild.members if not m.bot]
    await interaction.response.send_message(
        f"📢 Tagging **{len(members)}** members...", ephemeral=True
    )

    # Discord messages have a 2000-character limit. Split mentions into
    # safe chunks and explicitly allow user mentions.
    chunks, current = [], ""
    for member in members:
        mention = f"{member.mention} "
        if len(current) + len(mention) > 1900:
            if current:
                chunks.append(current)
            current = mention
        else:
            current += mention

    if current:
        chunks.append(current)

    allowed = discord.AllowedMentions(users=True, everyone=False, roles=False, replied_user=False)
    for chunk in chunks:
        await interaction.followup.send(chunk, allowed_mentions=allowed)
        await asyncio.sleep(0.35)

@bot.tree.command(name="alltag", description="Mention all non-bot server members.")
async def alltag(interaction: discord.Interaction):
    await _tag_all_members(interaction)

@bot.tree.command(name="tagall", description="Alias: mention all non-bot server members.")
async def tagall(interaction: discord.Interaction):
    await _tag_all_members(interaction)


@bot.tree.command(name="channeladd", description="Allow music commands in this channel.")
async def channeladd(interaction: discord.Interaction):
    if not await require_admin(interaction): return
    allowed_channels.setdefault(interaction.guild.id, set()).add(interaction.channel_id)
    await interaction.response.send_message(f"✅ {interaction.channel.mention} added for music commands.")


@bot.tree.command(name="auth", description="Authorize a member to use music commands.")
@app_commands.describe(member="Member to authorize")
async def auth(interaction: discord.Interaction, member: discord.Member):
    if not await require_admin(interaction): return
    authorized.setdefault(interaction.guild.id, set()).add(member.id)
    await interaction.response.send_message(f"✅ {member.mention} is now authorized.")


@bot.tree.command(name="unauth", description="Remove a member's music authorization.")
@app_commands.describe(member="Member to unauthorize")
async def unauth(interaction: discord.Interaction, member: discord.Member):
    if not await require_admin(interaction): return
    authorized.setdefault(interaction.guild.id, set()).discard(member.id)
    await interaction.response.send_message(f"✅ {member.mention} is no longer authorized.")


@bot.tree.command(name="admins", description="List server administrators.")
async def admins(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("❌ Server only.")
    admins = [m.mention for m in interaction.guild.members if m.guild_permissions.administrator]
    await interaction.response.send_message("👑 **Admins**\n" + ("\n".join(admins) if admins else "None"))


@bot.tree.command(name="broadcast", description="Send an announcement to this group and DM server members.")
@app_commands.describe(message="Announcement text")
async def broadcast(interaction: discord.Interaction, message: str):
    if not await require_admin(interaction):
        return
    if not interaction.guild:
        await interaction.response.send_message("❌ This command only works in a server.", ephemeral=True)
        return

    # Show the group announcement immediately.
    embed = discord.Embed(
        title="📢 Server Broadcast",
        description=message,
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f"Sent by {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed)

    # DM server members. Bots are skipped and Discord's HTTP/rate-limit
    # handling is respected by awaiting each request.
    sent = 0
    failed = 0

    for member in interaction.guild.members:
        if member.bot:
            continue
        try:
            dm_embed = discord.Embed(
                title=f"📢 {interaction.guild.name}",
                description=message,
                color=discord.Color.blurple()
            )
            dm_embed.set_footer(text=f"Broadcast by {interaction.user.display_name}")
            await member.send(embed=dm_embed)
            sent += 1
            await asyncio.sleep(0.25)
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    await interaction.followup.send(
        f"✅ Broadcast complete. Group: **sent** | DMs delivered: **{sent}** | DMs unavailable: **{failed}**",
        ephemeral=True
    )


@bot.tree.command(name="gban", description="Ban a member from this server.")
@app_commands.describe(member="Member to ban", reason="Ban reason")
async def gban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await require_admin(interaction): return
    if member == interaction.user:
        return await interaction.response.send_message("❌ You cannot ban yourself.", ephemeral=True)
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        return await interaction.response.send_message("❌ That member has an equal/higher role.", ephemeral=True)
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Bot lacks permission or role hierarchy is blocking the ban.")


@bot.tree.command(name="help", description="Show bot commands.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🎵 Music Bot", description="Music + moderation + server tools")
    embed.add_field(name="Music", value="`/play` `/vplay` `/start` `/pause` `/stop` `/skip` `/queue` `/shuffle` `/speed` `/seek` `/seekback` `/nowplaying`", inline=False)
    embed.add_field(name="Server", value="`/channeladd` `/auth` `/unauth` `/admins` `/broadcast` `/gban` `/alltag` `/tagall` `/id` `/ping`", inline=False)
    await interaction.response.send_message(embed=embed)


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from environment variables.")

bot.run(TOKEN)
