import discord

from notorious_discord_bot.cogs.music.util.ytdl_source import YTDLSource

class Song:
    __slots__ = ("source", "requester")

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (
            discord.Embed(
                title="Now playing",
                description="```css\n{0.source.title}\n```".format(self),
                color=discord.Color.blurple(),
            )
            .add_field(name="Duration", value=self.source.duration)
            .add_field(name="Requested by", value=self.requester.mention)
            .add_field(
                name="Uploader",
                value="[{0.source.uploader}]({0.source.uploader_url})".format(self),
            )
            .add_field(name="URL", value="[Click]({0.source.url})".format(self))
            .set_thumbnail(url=self.source.thumbnail)
        )

        return embed
