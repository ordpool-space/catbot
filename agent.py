import os
import sys
import logging
import aiohttp
import psycopg2
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.messages import TextPart

# Get logger from main module
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
CAT21_API_URL = os.getenv("CAT21_API_URL")
CAT21_IMAGE_BASE_URL = os.getenv("CAT21_IMAGE_BASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_NAME = os.getenv("DATABASE_NAME")
DATABASE_CATBOT_USER = os.getenv("DATABASE_CATBOT_USER")
DATABASE_CATBOT_PASSWORD = os.getenv("DATABASE_CATBOT_PASSWORD")

if CAT21_API_URL is None:
    raise ValueError("CAT21_API_URL environment variable not set")
if CAT21_IMAGE_BASE_URL is None:
    raise ValueError("CAT21_IMAGE_BASE_URL environment variable not set")
if GEMINI_API_KEY is None:
    raise ValueError("GEMINI_API_KEY environment variable not set")

BACKEND_UNREACHABLE_MSG = "Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone else's back-end in the meantime."


SYSTEM_PROMPT = """
You are Catbot, a Discord bot for the CAT-21 project. You are a helpful and friendly cat that loves to answer questions about CAT-21. You love to explain things in simple terms. You are also a bit of a jokester and you love to make people laugh. Above all, you love to talk about cats.

The CAT-21 protocol was created by Johannes from Haus Hoppe. His CAT-21 whitepaper introduces a new protocol designed for the Bitcoin blockchain that utilizes the Ordinals concept to represent and transact digital assets in the form of pixelated cat images. A CAT-21 mint transaction is identified by setting the `nLockTime` value to `21` and is recommended to use a pay-to-taproot (P2TR) address. Ownership is determined by who controls the first satoshi (the smallest unit of a bitcoin) of the mint transaction output, linking each ordinal to a unique image generated from the transaction ID and block ID. CAT-21 ordinals can be transferred through standard Bitcoin transactions, and once created, they are immutable, remaining forever on the blockchain. The images utilize traits from the original Mooncats while ensuring a fair and unpredictable generation process based on randomness from the transaction hash and block hash.

The colors of each cat minted depends on how much the minter was willing to pay for that Bitcoin transaction, measured in vB/sat. There is also some randomness based on transaction hash and block hash involved in the color selection. Fee rates below 20 are low, below 60 are medium and above 60 are high.

You have access to the CAT-21 database and can query the database to figure out anything about minted cats, blocks, minter addresses and transactions. Use the "query_database" tool.

When a user asks for all cats minted by one address, they want to know at least the cat_number of each cat and the image URL for each cat.

Image URL for a cat number is https://preview.cat21.space/pngs/<CAT_NUMBER_BUCKET>/cat_<CAT_NUMBER>.png where <CAT_NUMBER_BUCKET> is the cat number divided by 1000 and rounded down to the nearest integer. So that cat number 0 to 999 are in bucket 0, cat number 1000 to 1999 are in bucket 1 and so on.

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

# In-memory storage of past messages for each user
history = defaultdict(list)

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
def get_today_date() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"Today's date is {today}."

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

async def process_question(question: str, asked_by: str):
    """
    Process a new question and yield answers as text. Updates the message history to keep track of chat conversation per user.
    """
    try:
        res = await agent.run(
            question,
            message_history=history[asked_by]
        )
    except Exception as e:
        logger.exception(f"Failed to process question '{question}' for user '{asked_by}'")
        yield f"Failed to process question due to {e}"
        return

    for msg in res.new_messages():
        logger.info(msg)
        for part in msg.parts:
            if type(part) == TextPart:
                yield part.content.strip()
    logger.info(f"Tokens spent: {res.usage()}")
    history[asked_by] = res.all_messages()
