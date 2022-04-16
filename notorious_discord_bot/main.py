import os

from discord.ext import commands
from dotenv import load_dotenv
from loguru import logger

from notorious_discord_bot.cogs.music.music import Music

load_dotenv()

bot = commands.Bot(
    # command_prefix=commands.when_mentioned_or("!"), description="A bot to play music with, as well as some other stuff. Run !help to see what all I can do."
        command_prefix=commands.when_mentioned_or("!"), description="A bot to play music with, as well as some other stuff. Run !help to see what all I can do."
)

@bot.event
async def on_ready():
    logger.info(f"Logged on as {bot.user}")


bot.add_cog(Music(bot))
bot.run(os.getenv("DISCORD_TOKEN"))
