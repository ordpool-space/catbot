import os
import sys
import discord
import logging
from discord.ext import commands
from dotenv import load_dotenv
from logging.handlers import TimedRotatingFileHandler

from agent import CatbotAgent

# Create a logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.INFO)

# Create handlers
console_handler = logging.StreamHandler(sys.stdout)
file_handler = TimedRotatingFileHandler(
    "/data/logs/catbot.log", when="midnight", interval=1
)
file_handler.suffix = "%Y-%m-%d"

# Create a logging format
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%d-%b-%y %H:%M:%S"
)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)
discord_logger.addHandler(console_handler)
discord_logger.addHandler(file_handler)

# Load environment variables
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if DISCORD_BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set")

BACKEND_UNREACHABLE_MSG = "Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone else's back-end in the meantime."
PROCESSING_ERROR_MSG = "Uh-oh, our stupid dog ate the answer. Please try again."

# Remove "Arguments:" from help command output
help_cmd = commands.DefaultHelpCommand(show_parameter_descriptions=False)

# Initialize the bot with command prefix '!'
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="CAT-21 Discord Bot",
    case_insensitive=True,
    strip_after_prefix=True,
    help_command=help_cmd,
)

# Initialize the agent outside question scope to avoid reinitialization
agent = CatbotAgent()

# Block all DMs
@bot.check
async def globally_block_dms(ctx):
    return ctx.guild is not None

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        help_text = "Uh-oh! Discord says you have to use !c in front of your question to get my attention. Zoom zoom!"
        await ctx.send(help_text)


@bot.command(
    name="c",
    brief="Ask me anything! What would you like to know?",
    help="""Ask me anything! I'm a bot and a cat and a catbot.
    I'll answer what you want to know about your minted cats, the CAT-21 project and more!""",
)
async def c(ctx, *, question):
    requester_info = f"'{ctx.author.name}' ({ctx.author.id})"
    guild_info = f"'{ctx.guild.name}' ({ctx.guild.id})" if ctx.guild else "DM"
    logger.info(f'Got "!c {question}" from {requester_info} in {guild_info}')

    if not question.strip():
        await ctx.send("I'm a bot and a cat and a catbot. Ask me anything!")
        return

    try:
        async for answer in agent.process_question(question, requester_info):
            await ctx.send(answer)
    except Exception as e:
        logger.exception(f"Error processing question '{question}'")
        await ctx.send(PROCESSING_ERROR_MSG)

if __name__ == "__main__":
    # Run the bot
    bot.run(DISCORD_BOT_TOKEN)
