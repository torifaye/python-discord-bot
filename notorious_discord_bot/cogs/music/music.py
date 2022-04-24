import asyncio
import math
import re
from typing import Literal
from wavelink import Equalizer, Filter, SearchableTrack
from wavelink.ext import spotify
import os
import discord

from discord.ext import commands
from discord.commands import Option, slash_command
from loguru import logger

import wavelink

from notorious_discord_bot.cogs.music.util.ytdl_source import YTDLSource


SHORT_DELAY = 5.0
NORMAL_DELAY = 10.0
LONG_DELAY = 30.0

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
       self.bot = bot
       bot.loop.create_task(self.connect_lavalink_nodes())

    async def connect_lavalink_nodes(self):
        """Connect to lavalink node"""
        await self.bot.wait_until_ready()
        
        node = await wavelink.NodePool.create_node(
            bot=self.bot, host="0.0.0.0", port=2333, password=os.getenv("WAVELINK_PW"),
            spotify_client=spotify.SpotifyClient(
                client_id=os.getenv("SPOTIFY_CLIENT_ID"), 
                client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"))
        )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        """Event fired when a node has finished connecting"""
        logger.info(f"Lavalink Node: <{node.identifier}> is ready")


    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage(
                "This command can't be used in direct messages."
            )

        return True

    async def cog_command_error(self, ctx: discord.ApplicationContext, error: discord.ApplicationCommandError):
        await ctx.send(f"An error occurred: {str(error)}")

    @slash_command(name="join", invoke_without_subcommand=True)
    async def _join(self, ctx: discord.ApplicationContext):
        """Joins a voice channel."""
        destination = ctx.author.voice.channel
        await destination.connect(cls=wavelink.Player)

    @slash_command(name="play")
    async def _play(self, ctx: discord.ApplicationContext, *, query: Option(str, "Song source (e.g. youtube link, spotify link, plain search query)")):
        """Plays a video from youtube. Can handle youtube links and general search queries."""
        if not ctx.voice_client:
            await ctx.invoke(self._join)

        youtube_regex = 'https:\/\/www.youtube.com\/(watch\?v=.*|playlist\?list=.*)|https:\/\/youtu.be\/.*'
        spotify_regex = 'https:\/\/open.spotify.com\/(track|album|playlist)\/(.+)\?si=.+'

        vc: wavelink.Player = ctx.voice_client
        vc.ctx = ctx
        if not vc.loop:
            setattr(vc, "loop", False)
        if not vc.bass:
            setattr(vc, "bass", "off")

        if match := re.match(youtube_regex, query):
            logger.info(f"YOUTUBE MATCH: {match.groups}")
            if 'watch' in match.group(1):
                result = await wavelink.YouTubeTrack.search(query)
                await vc.queue.put_wait(result)
            if 'list' in match.group(1):
                playlist = await vc.node.get_playlist(wavelink.YouTubePlaylist, query) 
                for song in playlist.tracks:
                    vc.queue.put(song)      
                response = await ctx.respond(f"Added **{len(playlist.tracks)}** song{'s' if len(playlist.tracks) > 1 else ''} to the queue")
                await response.delete_original_message(delay=SHORT_DELAY)
        elif groups := re.match(spotify_regex, query):
            logger.info(groups)
            async for track in (tracks := spotify.SpotifyTrack.iterator(query=query, partial_tracks=True)):
                vc.queue.put(track)
            response = await ctx.respond(f"Added **{tracks._count}** songs to the queue")
            await response.delete_original_message(delay=SHORT_DELAY)
        else:
            result = await wavelink.YouTubeTrack.search(query, return_first=True)
            await vc.queue.put_wait(result)

        if not vc.is_playing():
            next_up = vc.queue.get()
            next_song = await next_up._search() if type(next_up).__name__ == "PartialTrack" else next_up
            await vc.play(next_song)
            embed = await ctx.send(embed=self.create_embed(next_song, ctx))
            await embed.delete(delay=LONG_DELAY)

        vc.ctx = ctx
        setattr(vc, "loop", False)

    @slash_command(name="pause")
    async def _pause(self, ctx: discord.ApplicationContext):
        """Pauses currently playing track."""
        vc: wavelink.Player = ctx.voice_client
        if vc.is_playing():
            await vc.pause()
            response = await ctx.respond(f"Paused at {self.parse_duration(vc.position)}/{self.parse_duration(vc.track.duration)}")
            await response.delete_original_message(delay=NORMAL_DELAY)

    @slash_command(name="resume")
    async def _resume(self, ctx: discord.ApplicationContext):
        """Resumes currently playing track."""
        vc: wavelink.Player = ctx.voice_client
        if vc.is_paused():
            await vc.resume()
            response = await ctx.respond("⏯")
            await response.delete_original_message(delay=3.0)

    @slash_command(name="volume")
    async def _volume(self, ctx: discord.ApplicationContext, level: Option(int, "Volume to set to", min_value=0, max_value=300)):
        """Adjusts the volume of the bot."""
        vc: wavelink.Player = ctx.voice_client

        response = await ctx.respond(f"Adjusting volume from `{vc.volume}%` to `{level}%`")
        await response.delete_original_message(delay=NORMAL_DELAY)
        await vc.set_volume(level)

    @slash_command(name="skip")
    async def _skip(self, ctx: discord.ApplicationContext):
        """Skips currently playing track."""
        vc: wavelink.Player = ctx.voice_client
        await vc.seek(vc.track.length * 1000)
        response = await ctx.respond("Skipping song ⏭")
        await response.delete_original_message(delay=SHORT_DELAY)

    @slash_command(name="bass")
    async def _bassboost(self, ctx: commands.Context, level: Option(str, "Level of bass boost", choices=["off", "low", "medium", "high", "ultra", "maximum", "dummyhard"])):
        """Bass boosts currently playing track."""
        vc: wavelink.Player = ctx.voice_client

        presets = {
            "off": [(0, 0), (1, 0)],
            "low": [(0, 0.25), (1, 0.15)],
            "medium": [(0, 0.50), (1, 0.25)],
            "high": [(0, 0.75), (1, 0.50)],
            "ultra": [(0, 1), (1, 0.75)],
            "maximum": [(0, 1), (1, 1.0)],
            "dummyhard": [(0, 1.0), (1, 1.0), (2, 1.0), (3, 1.0), (4, 1.0)] 
        }


        await vc.set_filter(
            Filter(volume=vc.volume, equalizer=Equalizer(bands=presets[level])),
            seek=True
        )
        response = await ctx.respond(f"Bass changed from **{vc.bass}** to **{level}**")
        await response.delete_original_message(delay=NORMAL_DELAY)
        vc.bass = level

    @slash_command(name="stop")
    async def _stop(self, ctx: discord.ApplicationContext):
        """Stops voice client and disconnects."""
        vc: wavelink.Player = ctx.voice_client

        response = await ctx.respond("Stopping song ⏹")
        await response.delete_original_message(delay=NORMAL_DELAY)
        await vc.stop()
        await vc.disconnect(force=True)

    @slash_command(name="leave")
    async def _leave(self, ctx: discord.ApplicationContext):
        """Leaves voice channel."""
        vc: wavelink.Player = ctx.voice_client
        
        response = await ctx.respond("Goodbye!")
        await response.delete_original_message(delay=NORMAL_DELAY)
        await vc.disconnect(force=True)

    @slash_command(name="now")
    async def _nowplaying(self, ctx: discord.ApplicationContext):
        """Displays currently playing track."""
        response = await ctx.respond(embed=self.create_embed(ctx.voice_client.track, ctx))
        await response.delete_original_message(delay=LONG_DELAY)

    @slash_command(name="loop")
    async def _loop(self, ctx: discord.ApplicationContext):
        """Loops queue."""
        vc: wavelink.Player = ctx.voice_client

        try:
            vc.loop = not vc.loop
        except Exception:
            setattr(vc, "loop", True)

        response = await ctx.respond(f"Turned {'on' if vc.loop else 'off'} looping")
        await response.delete_original_message(delay=SHORT_DELAY)

    @slash_command(name="queue")
    async def _queue(self, ctx: discord.ApplicationContext, *, page: Option(int, "Page to go to", default=1)):
        """Displays current contents of queue."""
        vc: wavelink.Player = ctx.voice_client

        if vc.queue.is_empty:
            return await ctx.send("Empty queue.")
        
        items_per_page = 10
        pages = math.ceil(vc.queue.count / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ""
        for i, song in enumerate(list(vc.queue)[start:end], start=start):
            # queue += f"`{i+1}.` [**{song.title}**]({song.uri})\n"
            queue += f"`{i+1}.` {song.title}\n"

        embed = discord.Embed(
            description=f"**{vc.queue.count} tracks:**\n\n{queue}"
        ).set_footer(text=f"Viewing page {page}/{pages}")
        response = await ctx.respond(embed=embed)
        await response.delete_original_message(delay=LONG_DELAY)
            

    def create_embed(self, song: wavelink.YouTubeTrack, ctx: discord.ApplicationContext) -> discord.Embed:
        embed = (
            discord.Embed(
                title="Now Playing",
                description=f"```css\n{song.title}\n```",
                color=discord.Color.blurple()
            )
            .add_field(name="Duration", value=YTDLSource.parse_duration(int(song.length)))
            .add_field(name="Requested by", value=ctx.author)
            .add_field(name="Uploader", value=song.author)
            .add_field(name="URL", value=f"[Click]({song.uri})")
            .set_thumbnail(url=song.thumbnail)
        )

        return embed

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.Player, track: wavelink.Track, reason):
        ctx = player.ctx
        vc: wavelink.Player = ctx.voice_client

        if vc.queue.is_empty:
            return await vc.stop()

        if vc.loop:
            await vc.queue.put_wait(vc.track)

        next_up = vc.queue.get()

        next_song: wavelink.abc.Playable | None = await next_up._search() if type(next_up).__name__ == "PartialTrack" else next_up
        await vc.play(next_song)
        embed = await ctx.send(embed=self.create_embed(next_song, ctx))
        await embed.delete(delay=LONG_DELAY)

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("You are not connected to any voice channel!")
        
        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError("Bot is already in another voice channel, sorry :(")

    def parse_duration(self, duration: int | float, format: Literal["short", "long"] = "short"):
        minutes, seconds = divmod(round(duration), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append(f"{days} days")
        if hours > 0:
            duration.append(f"{hours} hours")
        if minutes > 0:
            duration.append(f"{minutes} minutes")
        if seconds > 0:
            duration.append(f"{seconds} seconds")

        match format:
            case "short":
                duration = [hours, minutes, seconds] if hours > 0 else [minutes, seconds]
                return ':'.join(map(lambda n: f'{n:02}', duration)) # Converts all entries array into string and leftpads 2
            case "long":
                return ', '.join(duration)
