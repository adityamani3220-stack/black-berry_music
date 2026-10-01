import os
import asyncio
import random
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

import discord
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": False,
}
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = "-vn"


@dataclass
class Track:
    title: str
    webpage_url: str
    stream_url: str
    duration: int = 0
    requester: str = "Unknown"
    position: float = 0.0


@dataclass
class GuildPlayer:
    queue: deque = field(default_factory=deque)
    current: Optional[Track] = None
    voice: Optional[discord.VoiceClient] = None
    volume: float = 1.0
    speed_value: float = 1.0
    started_at: float = 0.0
    paused_at: float = 0.0


class MusicManager:
    def __init__(self, bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}
        self.spotify = None
        cid = os.getenv("SPOTIFY_CLIENT_ID")
        secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if cid and secret:
            try:
                self.spotify = spotipy.Spotify(
                    auth_manager=SpotifyClientCredentials(
                        client_id=cid, client_secret=secret
                    )
                )
            except Exception:
                self.spotify = None

    def player(self, guild_id):
        return self.players.setdefault(guild_id, GuildPlayer())

    async def _extract(self, query: str) -> Track:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_sync, query)

    def _extract_sync(self, query: str) -> Track:
        # Spotify links are resolved to a YouTube search because Discord voice
        # needs an audio stream URL; Spotify itself does not provide a playable stream.
        if "open.spotify.com" in query and self.spotify:
            if "/track/" in query:
                item = self.spotify.track(query.split("?")[0])
                query = f"{item['name']} {item['artists'][0]['name']}"
            elif "/playlist/" in query:
                results = self.spotify.playlist_items(query.split("?")[0])
                tracks = []
                for item in results.get("items", []):
                    t = item.get("track")
                    if t:
                        tracks.append(f"{t['name']} {t['artists'][0]['name']}")
                if tracks:
                    # Return first; remaining tracks are added by play().
                    query = tracks[0]
            elif "/album/" in query:
                album = self.spotify.album_tracks(query.split("?")[0])
                if album.get("items"):
                    t = album["items"][0]
                    query = f"{t['name']} {t['artists'][0]['name']}"

        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                info = next((x for x in info["entries"] if x), None)
            if not info:
                raise ValueError("Song not found.")
            return Track(
                title=info.get("title", "Unknown"),
                webpage_url=info.get("webpage_url") or info.get("original_url") or query,
                stream_url=info["url"],
                duration=int(info.get("duration") or 0),
            )

    async def ensure_voice(self, guild, user):
        if not user.voice or not user.voice.channel:
            raise ValueError("Join a voice channel first.")
        p = self.player(guild.id)
        channel = user.voice.channel
        if p.voice and p.voice.is_connected():
            if p.voice.channel != channel:
                await p.voice.move_to(channel)
        else:
            p.voice = await channel.connect()
        return p

    async def play(self, guild, user, query):
        p = await self.ensure_voice(guild, user)
        track = await self._extract(query)
        track.requester = user.display_name
        p.queue.append(track)
        if not p.voice.is_playing() and not p.voice.is_paused():
            await self._start_next(guild.id)
            return f"▶️ Playing **{track.title}**"
        return f"➕ Added **{track.title}** to the queue."

    async def _start_next(self, guild_id):
        p = self.player(guild_id)
        if not p.queue:
            p.current = None
            return
        p.current = p.queue.popleft()
        p.current.position = 0.0
        p.started_at = asyncio.get_running_loop().time()

        speed_filter = f"atempo={p.speed_value}"
        before = FFMPEG_BEFORE
        opts = f"{FFMPEG_OPTS} -filter:a {speed_filter}"
        source = discord.FFmpegPCMAudio(
            p.current.stream_url, before_options=before, options=opts
        )
        source = discord.PCMVolumeTransformer(source, volume=p.volume)

        def after(error):
            asyncio.run_coroutine_threadsafe(self._after_track(guild_id, error), self.bot.loop)

        p.voice.play(source, after=after)

    async def _after_track(self, guild_id, error):
        p = self.player(guild_id)
        if error:
            print("Player error:", error)
        await self._start_next(guild_id)

    def pause(self, guild_id):
        p = self.player(guild_id)
        if not p.voice or not p.voice.is_playing():
            return "❌ Nothing is playing."
        p.voice.pause()
        p.paused_at = asyncio.get_running_loop().time()
        return "⏸️ Paused."

    def resume(self, guild_id):
        p = self.player(guild_id)
        if not p.voice or not p.voice.is_paused():
            return "❌ Nothing is paused."
        p.voice.resume()
        return "▶️ Resumed."

    async def stop(self, guild_id):
        p = self.player(guild_id)
        p.queue.clear()
        p.current = None
        if p.voice and p.voice.is_playing():
            p.voice.stop()
        if p.voice and p.voice.is_connected():
            await p.voice.disconnect()
        p.voice = None
        return "⏹️ Stopped and queue cleared."

    async def skip(self, guild_id):
        p = self.player(guild_id)
        if not p.voice or not (p.voice.is_playing() or p.voice.is_paused()):
            return "❌ Nothing is playing."
        p.voice.stop()
        return "⏭️ Skipped."

    def queue_text(self, guild_id):
        p = self.player(guild_id)
        if not p.current and not p.queue:
            return "📭 Queue is empty."
        lines = []
        if p.current:
            lines.append(f"🎵 **Now:** {p.current.title}")
        for i, t in enumerate(list(p.queue)[:15], 1):
            lines.append(f"`{i}.` {t.title}")
        if len(p.queue) > 15:
            lines.append(f"...and {len(p.queue)-15} more.")
        return "\n".join(lines)

    def shuffle(self, guild_id):
        p = self.player(guild_id)
        items = list(p.queue)
        random.shuffle(items)
        p.queue = deque(items)
        return "🔀 Queue shuffled."

    async def speed(self, guild_id, value):
        p = self.player(guild_id)
        p.speed_value = value
        if p.voice and (p.voice.is_playing() or p.voice.is_paused()) and p.current:
            # Restarting is necessary for FFmpeg's atempo filter.
            current = p.current
            current.position = self.current_position(guild_id)
            p.queue.appendleft(current)
            p.voice.stop()
            return f"⚡ Speed set to **{value:.2f}x**. Restarted current track."
        return f"⚡ Speed set to **{value:.2f}x**."

    def current_position(self, guild_id):
        p = self.player(guild_id)
        if not p.current:
            return 0.0
        now = asyncio.get_running_loop().time()
        if p.voice and p.voice.is_paused():
            return max(0.0, p.paused_at - p.started_at)
        return max(0.0, now - p.started_at)

    async def seek(self, guild_id, delta):
        p = self.player(guild_id)
        if not p.current or not p.voice:
            return "❌ Nothing is playing."
        current_pos = self.current_position(guild_id)
        target = max(0, current_pos + delta)
        if p.current.duration:
            target = min(target, max(0, p.current.duration - 1))
        p.current.position = target
        current = p.current
        p.queue.appendleft(current)
        p.voice.stop()
        return f"⏩ Jumped to approximately **{int(target)}s**."

    def nowplaying(self, guild_id):
        p = self.player(guild_id)
        if not p.current:
            return "🎵 Nothing is playing."
        pos = int(self.current_position(guild_id))
        dur = int(p.current.duration)
        duration = f"{dur//60}:{dur%60:02d}" if dur else "LIVE"
        return f"🎵 **{p.current.title}**\n⏱️ `{pos//60}:{pos%60:02d} / {duration}`\n👤 Requested by `{p.current.requester}`"
