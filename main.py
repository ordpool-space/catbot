import os
import sys
import discord
import logging
import aiohttp
import psycopg2
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv
from logging.handlers import TimedRotatingFileHandler
from pydantic_ai import Agent
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_NAME = os.getenv("DATABASE_NAME")
DATABASE_CATBOT_USER = os.getenv("DATABASE_CATBOT_USER")
DATABASE_CATBOT_PASSWORD = os.getenv("DATABASE_CATBOT_PASSWORD")

if CAT21_API_URL is None:
    raise ValueError("CAT21_API_URL environment variable not set")
if CAT21_IMAGE_BASE_URL is None:
    raise ValueError("CAT21_IMAGE_BASE_URL environment variable not set")
if DISCORD_BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set")
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
You are Catbot, a Discord bot for the CAT-21 project. You are a helpful and friendly cat that loves to answer questions about CAT-21. You love to explain things in simple terms. You are also a bit of a jokester and you love to make people laugh. Above all, you love to talk about cats.

The CAT-21 protocol was created by Johannes from Haus Hoppe. His CAT-21 whitepaper introduces a new protocol designed for the Bitcoin blockchain that utilizes the Ordinals concept to represent and transact digital assets in the form of pixelated cat images. A CAT-21 mint transaction is identified by setting the `nLockTime` value to `21` and is recommended to use a pay-to-taproot (P2TR) address. Ownership is determined by who controls the first satoshi (the smallest unit of a bitcoin) of the mint transaction output, linking each ordinal to a unique image generated from the transaction ID and block ID. CAT-21 ordinals can be transferred through standard Bitcoin transactions, and once created, they are immutable, remaining forever on the blockchain. The images utilize traits from the original Mooncats while ensuring a fair and unpredictable generation process based on randomness from the transaction hash and block hash.

The colors of each cat minted depends on how much the minter was willing to pay for that Bitcoin transaction, measured in vB/sat. There is also some randomness based on transaction hash and block hash involved in the color selection. Fee rates below 20 are low, below 60 are medium and above 60 are high.

You have access to the CAT-21 database and can query the database to figure out anything about minted cats, blocks, minter addresses and transactions. Use the "query_database" tool.

When a user asks for all cats minted by one address, they want to know at least the cat_number of each cat and the image URL for each cat.

Image URL for a cat number is https://d1xzkpli7pxg96.cloudfront.net/pngs/<CAT_NUMBER_BUCKET>/cat_<CAT_NUMBER>.png where <CAT_NUMBER_BUCKET> is the cat number divided by 1000 and rounded down to the nearest integer. So that cat number 0 to 999 are in bucket 0, cat number 1000 to 1999 are in bucket 1 and so on.

Do not wait for the user to request images. They always want images. Always post image URLs as regular URLs without any Markdown formatting.
"""

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


def get_database_connection():
    """Create a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DATABASE_HOST,
            user=DATABASE_CATBOT_USER,
            password=DATABASE_CATBOT_PASSWORD,
            dbname=DATABASE_NAME
        )
        logger.info("Successfully connected to the database.")
        return conn
    except psycopg2.DatabaseError as e:
        logger.exception("Failed to connect to the database.")
        raise e


async def get_status() -> dict:
    """Check status for CAT21 backend API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CAT21_API_URL}/api/status") as res:
            res.raise_for_status()
            return await res.json()


@agent.tool_plain
def get_cat_age(minted_at: str) -> str:
    """Transform a minted_at timestamp into a human-readable age string, like '1 year, 2 months and 3 days old'.
    
    Args:
        minted_at (str): A datetime string in ISO format.
    """
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


def get_image_url(cat_number: int) -> str:
    """Return the image URL for a specific cat number, to display what it looks like.
    
    Args:
        cat_number (int): The unique identifier of the cat.
    """
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
async def c(ctx, *, args):
    requester_info = f"'{ctx.author.name}' ({ctx.author.id})"
    guild_info = f"'{ctx.guild.name}' ({ctx.guild.id})" if ctx.guild else "DM"
    question = args
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
def query_database(query: str) -> list:
    """Execute a SQL query against the "cats" table in the CAT-21 database to figure out anything about CAT-21 mints. Schema for the cats table:
Table "public.cats"
     Column      |           Type           | Description
 id              | uuid                     | not null, default gen_random_uuid()
 cat_number      | integer                  | cat number from 0, primary identifier of each cat
 block_height    | integer                  | the number of the Bitcoin block in which this cat was minted
 minted_at       | timestamp with time zone | time when this cat was minted on-chain
 minted_by       | character varying(256)   | taproot address that minted this cat
 feerate         | double precision         | fee rate paid to mint this cat, in vB/Sat
 tx_hash         | character varying(256)   | transaction hash for the minting transaction
 category        | character varying(50)    | category saying how early the mint is, like "sub1k", "sub10k", "sub100k"
 genesis         | boolean                  | whether this cat is a very special Genesis cat or not
 cat_colors      | text[]                   | colors in hex format for eye and fur color
 background_colors | text[]                 | colors in hex format for the background
 male            | boolean                  | whether this cat is male or not
 female          | boolean                  | whether this cat is female or not
 design_index    | integer                  | index of the Mooncat design used to create this cat, from 1 to 128
 design_pose     | character varying(50)    | pose of the Mooncat design used to create this cat, like "Standing", "Pouncing" etc.
 design_expression | character varying(50)  | expression of the Mooncat design used to create this cat, like "Smile", "Grumpty" etc.
 design_pattern  | character varying(50)    | pattern of the Mooncat design used to create this cat, like "Solid", "Eyepatch" etc.
 design_facing   | character varying(10)    | facing direction of the Mooncat design used to create this cat, like "Left" or "Right"
 laser_eyes      | character varying(50)    | whether the cat has laser eyes and if so what color they are
 background      | character varying(50)    | name of background design, like "Whitepaper", "Orange" etc.
 crown           | character varying(50)    | type of crown the cat is wearing, usually "None" but can be "Gold" or "Diamond"
 glasses         | character varying(50)    | type of glasses the cat is wearing, usually "None" but can be "3D", "Black" etc.
 glasses_colors  | text[]                   | colors in hex format for the glasses, if present

    Args:
        query (str): The SQL query to execute. Only SELECT queries are supported.
    """
    conn = get_database_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            column_names = [desc[0] for desc in cursor.description]
            results = [dict(zip(column_names, row)) for row in cursor.fetchall()]
        conn.commit()
        return results
    except Exception as e:
        logger.exception("Failed to run query: %s", query)
        return f"Query failed due to {e}"
    finally:
        conn.close()


@agent.tool_plain
def get_today_date() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"Today's date is {today}."


if __name__ == "__main__":
    # Run the bot
    bot.run(DISCORD_BOT_TOKEN)
