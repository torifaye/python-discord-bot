import math
from wavelink import Equalizer, Filter
import os
import discord

from discord.ext import commands
from loguru import logger

import wavelink

from notorious_discord_bot.cogs.music.util.ytdl_source import YTDLSource

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
       self.bot = bot 
       self.voice_states = {}

       bot.loop.create_task(self.connect_lavalink_nodes())

    async def connect_lavalink_nodes(self):
        """Connect to lavalink node"""
        await self.bot.wait_until_ready()
        
        node = await wavelink.NodePool.create_node(
            bot=self.bot, host="0.0.0.0", port=2333, password=os.getenv("WAVELINK_PW")
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

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send(f"An error occurred: {str(error)}")

    @commands.command(name="join", invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context):
        """Joins a voice channel."""
        destination = ctx.author.voice.channel
        self.voice_states[ctx.guild.id] = await destination.connect(cls=wavelink.Player)

    @commands.command(name="play")
    async def _play(self, ctx: commands.Context, *, search: wavelink.YouTubeTrack):
        """Plays a video from youtube. Can handle youtube links and general search queries."""
        if not ctx.voice_client:
            await ctx.invoke(self._join)

        vc: wavelink.Player = ctx.voice_client
        setattr(vc, "loop", False)

        if vc.queue.is_empty and not vc.is_playing():
            await vc.play(search)
            await ctx.send(embed=self.create_embed(search, ctx))
        else:
            await vc.queue.put_wait(search)
            await ctx.send(f"Added **{search.title}** by **{search.author}** to the queue")

        vc.ctx = ctx
        setattr(vc, "loop", False)

    @commands.command(name="pause")
    async def _pause(self, ctx: commands.Context):
        """Pauses currently playing track."""
        vc: wavelink.Player = ctx.voice_client
        if vc.is_playing():
            await vc.pause()
            await ctx.message.add_reaction("⏯")

    @commands.command(name="resume")
    async def _resume(self, ctx: commands.Context):
        """Resumes currently playing track."""
        vc: wavelink.Player = ctx.voice_client
        if vc.is_paused():
            await vc.resume()
            await ctx.message.add_reaction("⏯")

    @commands.command(name="volume")
    async def _volume(self, ctx: commands.Context, level: int):
        """Adjusts the volume of the bot."""
        vc: wavelink.Player = ctx.voice_client

        async with ctx.typing():
            if 0 < level < 300:
                await ctx.send(f"Adjusting volume from `{vc.volume}%` to `{level}%`")
                await vc.set_volume(level)
            else:
                await ctx.send("Volume must be within 0% to 300%")

    @commands.command(name="skip")
    async def _skip(self, ctx: commands.Context):
        """Skips currently playing track."""
        vc: wavelink.Player = ctx.voice_client
        await vc.seek(vc.track.length * 1000)
        await ctx.message.add_reaction("⏭")

    @commands.command(name="bass")
    async def _bassboost(self, ctx: commands.Context, level: str):
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

        if level not in presets.keys():
            return await ctx.send(f"Preset provided must be one of: {', '.join(list(presets.keys())[:-1])}")

        try:
            await vc.set_filter(
                Filter(volume=vc.volume, equalizer=Equalizer(bands=presets[level])),
                seek=True
            )
        except ValueError:
            pass

    @commands.command(name="stop")
    async def _stop(self, ctx: commands.Context):
        """Stops voice client and disconnects."""
        vc: wavelink.Player = ctx.voice_client

        await vc.stop()
        await vc.disconnect(force=True)
        await ctx.message.add_reaction("⏹")

    @commands.command(name="leave")
    async def _leave(self, ctx: commands.Context):
        """Leaves voice channel."""
        vc: wavelink.Player = ctx.voice_client

        await vc.disconnect(force=True)

    @commands.command(name="now")
    async def _nowplaying(self, ctx: commands.Context):
        """Displays currently playing track."""
        await ctx.send(embed=self.create_embed(ctx.voice_client.track, ctx))

    @commands.command(name="loop")
    async def _loop(self, ctx: commands.Context):
        """Loops queue."""
        vc: wavelink.Player = ctx.voice_client

        try:
            vc.loop = not vc.loop
        except Exception:
            setattr(vc, "loop", True)

        await ctx.reply(f"Turned {'on' if vc.loop else 'off'} looping")

    @commands.command(name="queue")
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
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
            queue += f"`{i+1}.` [**{song.title}**]({song.uri})\n"

        embed = discord.Embed(
            description=f"**{vc.queue.count} tracks:**\n\n{queue}"
        ).set_footer(text=f"Viewing page {page}/{pages}")
        await ctx.send(embed=embed)
            

    def create_embed(self, song: wavelink.YouTubeTrack, ctx: commands.Context) -> discord.Embed:
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

        next_song = vc.queue.get()
        await vc.play(next_song)
        await ctx.send(embed=self.create_embed(next_song, ctx))

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("You are not connected to any voice channel!")
        
        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError("Bot is already in another voice channel, sorry :(")
