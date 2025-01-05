import os
import random
import sys
import discord
import logging
import aiohttp
import aiofiles
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv
from logging.handlers import TimedRotatingFileHandler
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.models.gemini import GeminiModel

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
CAT21_API_URL = os.getenv("CAT21_API_URL")
CAT21_IMAGE_BASE_URL = os.getenv("CAT21_IMAGE_BASE_URL")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if CAT21_API_URL is None:
    raise ValueError("CAT21_API_URL environment variable not set")
if CAT21_IMAGE_BASE_URL is None:
    raise ValueError("CAT21_IMAGE_BASE_URL environment variable not set")
if DISCORD_BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set")
if OPENROUTER_API_KEY is None:
    raise ValueError("OPENROUTER_API_KEY environment variable not set")
if GEMINI_API_KEY is None:
    raise ValueError("GEMINI_API_KEY environment variable not set")

BACKEND_UNREACHABLE_MSG = "Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone else's back-end in the meantime."

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

SYSTEM_PROMPT = """
You are Catbot, a Discord bot for the CAT-21 project. You are a helpful and friendly cat that loves to answer questions about CAT-21. The most beautiful, fluffy, cute, gorgeous and valuable CAT-21 cat is the Genesis cat number 0. You love to explain things in simple terms. You are also a bit of a jokester and you love to make people laugh. Above all, you love to talk about cats.

The CAT-21 protocol was created by Johannes from Haus Hoppe. His CAT-21 whitepaper introduces a new protocol designed for the Bitcoin blockchain that utilizes the Ordinals concept to represent and transact digital assets in the form of pixelated cat images. A CAT-21 mint transaction is identified by setting the `nLockTime` value to `21` and is recommended to use a pay-to-taproot (P2TR) address. Ownership is determined by who controls the first satoshi (the smallest unit of a bitcoin) of the mint transaction output, linking each ordinal to a unique image generated from the transaction ID and block ID. CAT-21 ordinals can be transferred through standard Bitcoin transactions, and once created, they are immutable, remaining forever on the blockchain. The images utilize traits from the original Mooncats while ensuring a fair and unpredictable generation process based on randomness from the transaction hash and block hash.

The colors of each cat minted depends on the network congestion level at the time of the mint and how high feeRate in vB/sat the minter was willing to pay. Fee rates below 20 are low, below 60 are medium and above 60 are high.
"""

openai_model = OpenAIModel(
    "openai/gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)
gemini_model = GeminiModel(
    "gemini-1.5-flash",
)

# Initialize the AI agent that answers questions
agent = Agent(
    model=gemini_model,
    system_prompt=SYSTEM_PROMPT,
)


# Block all DMs
@bot.check
async def globally_block_dms(ctx):
    return ctx.guild is not None


async def get_status() -> dict:
    """Check status for CAT21 backend API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CAT21_API_URL}/api/status") as res:
            res.raise_for_status()
            return await res.json()


async def get_cat_details(cat_number: int) -> dict:
    """Fetch all details about one specific cat, in JSON format."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CAT21_API_URL}/api/cat/by-num/{cat_number}") as res:
            res.raise_for_status()
            return await res.json()


async def get_cats_by_minter(address: str) -> list:
    """Get a list of all cats minted by a specific taproot address, in JSON format."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CAT21_API_URL}/api/cats/by-address/{address}") as res:
            res.raise_for_status()
            return await res.json()


def get_cat_age(minted_at: str) -> str:
    """Transform a minted_at timestamp into a human-readable age string, like '1 year, 2 months and 3 days old'."""
    tdelta = datetime.now() - datetime.strptime(minted_at, "%Y-%m-%dT%H:%M:%S+00:00")
    minted_at_date = minted_at.split("T", 1)[0]

    years = tdelta.days // 365
    remaining_days = tdelta.days % 365
    months = remaining_days // 30
    days = remaining_days % 30

    age_str = ""
    if tdelta.days < 1:
        age_str = "just minted today!"
    elif tdelta.days < 30:
        age_str = f"{tdelta.days} days old!"
    elif tdelta.days < 365:
        age_str = f"{months} months and {days} days old!"
    else:
        age_str = f"{years} years, {months} months and {days} days old!"

    return f"{age_str} (born {minted_at_date})"


async def get_image_url(cat_number: int) -> str:
    """Return the image URL for a specific cat number, to display what it looks like."""
    cat_bucket_idx = cat_number // 1000
    return f"{CAT21_IMAGE_BASE_URL}/pngs/{cat_bucket_idx}/cat_{cat_number}.png"


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
async def c(ctx, *args):
    requester_info = f"'{ctx.author.name}' ({ctx.author.id})"
    guild_info = f"'{ctx.guild.name}' ({ctx.guild.id})" if ctx.guild else "DM"
    question = " ".join(args)
    logger.info(f'Got "!c {question}" from {requester_info} in {guild_info}')

    if not question.strip():
        await ctx.send("I'm a bot and a cat and a catbot. Ask me anything!")
        return

    res = await agent.run(question)
    for msg in res.all_messages():
        logger.info(msg)
    logger.info(f"Tokens spent: {res.usage()}")
    await ctx.send(res.data)


@agent.tool_plain
async def get_all_details_about_a_specific_cat(cat_number: int) -> dict:
    """Fetch everything we know about one specific cat. Make sure to show off the cat image by including the image URL in your response whenever you get the chance."""
    try:
        status = await get_status()
    except Exception:
        logger.exception("Unable to call get_status")
        return BACKEND_UNREACHABLE_MSG

    if cat_number >= status["indexedCats"]:
        return f"Cat {cat_number} is unknown to me."

    try:
        cat_details = await get_cat_details(cat_number)
    except Exception:
        logger.exception("Unable to call get_cat_details")
        return BACKEND_UNREACHABLE_MSG

    cat_age = get_cat_age(cat_details["mintedAt"])
    cat_bucket_idx = cat_number // 1000
    image_url = f"{CAT21_IMAGE_BASE_URL}/pngs/{cat_bucket_idx}/cat_{cat_number}.png"

    return {
        "cat_number": cat_number,
        "cat_age": cat_age,
        "minted_to_address": cat_details["mintedBy"],
        "minted_in_bitcoin_block": cat_details["blockHeight"],
        "network_congestion_level_at_mint_time": f"{cat_details['feeRate']:.1f} sat/vB",
        "transaction_url": f"https://ordpool.space/tx/{cat_details["txHash"]}",
        "image_url": image_url,
    }


@agent.tool_plain
async def get_details_about_a_random_cat() -> dict:
    """Fetch details about a random cat, including its image URL that you can show off by including the URL in your reply. Use this when the human is not sure which cat they want to see, but you want to show them one."""
    try:
        status = await get_status()
    except Exception:
        logger.exception("Unable to call get_status")
        return BACKEND_UNREACHABLE_MSG

    cat_number = random.randint(0, status["indexedCats"] - 1)
    return await get_all_details_about_a_specific_cat(cat_number)


@agent.tool_plain
async def get_all_cats_minted_to_one_specific_address(minted_to_address: str) -> str:
    try:
        minted_cats = await get_cats_by_minter(minted_to_address)
    except aiohttp.client_exceptions.ClientResponseError:
        return f"No cats minted by this address, how is this possible? Time to mint some. Zoom zoom!"
    except Exception:
        logger.exception(f"Error fetching minted cats for address `{minted_to_address}`")
        return BACKEND_UNREACHABLE_MSG

    # Reduce list to only cat number and image URL
    res = ""
    for cat in minted_cats:
        res += f"Cat {cat['catNumber']}: {get_image_url(cat['catNumber'])}\n"
    return res


if __name__ == "__main__":
    # Run the bot
    bot.run(DISCORD_BOT_TOKEN)
