import os
import random
import sys
import discord
import logging
import aiohttp
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    stream=sys.stdout,
)

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CAT21_API_URL = os.getenv("CAT21_API_URL")
CAT21_IMAGE_BASE_URL = os.getenv("CAT21_IMAGE_BASE_URL")

if DISCORD_BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set")

# Initialize the bot with command prefix '!'
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="CAT-21 Discord Bot",
    case_insensitive=True,
    strip_after_prefix=True,
)


async def get_status() -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CAT21_API_URL}/api/status") as res:
            res.raise_for_status()
            return await res.json()


async def get_cat_details(cat_number: int) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CAT21_API_URL}/api/cat/by-num/{cat_number}") as res:
            res.raise_for_status()
            return await res.json()


async def get_cats_by_minter(address: str) -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CAT21_API_URL}/api/cats/by-address/{address}") as res:
            res.raise_for_status()
            return await res.json()


def get_cat_age(minted_at: str) -> str:
    tdelta = datetime.now() - datetime.strptime(minted_at, "%Y-%m-%dT%H:%M:%S+00:00")
    minted_at_date = minted_at.split('T', 1)[0]

    age_str = ""
    if tdelta.days == 0:
        age_str = "just minted today!"
    elif tdelta.days < 30:
        age_str = f"{tdelta.days} days old!"
    elif tdelta.days < 365:
        age_str = f"{tdelta.days // 30} months old!"
    else:
        age_str = f"{tdelta.days // 365} years {tdelta.days // 30} months old!"

    return f"{age_str} (born {minted_at_date})"


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def cat(ctx, identifier: str = ""):
    logging.info(f"!cat {identifier} from '{ctx.author.name}' ID {ctx.author.id}")

    try:
        status = await get_status()
    except:
        await ctx.send(
            "Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone else's back-end in the meantime."
        )
        logging.exception("Unable to call get_status")
        return

    if identifier.isdigit() and int(identifier) >= 0:
        cat_number = int(identifier)
    else:
        cat_number = random.randint(0, status["indexedCats"] - 1)

    if cat_number > status["indexedCats"]:
        await ctx.send(
            f"Cat {cat_number} unknown to me. If it's newly minted, ping @ethspresso to update me about it."
        )
        return

    try:
        cat_details = await get_cat_details(cat_number)
    except:
        await ctx.send(
            "Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone else's back-end in the meantime."
        )
        logging.exception("Unable to call get_cat_details")
        return

    cat_age = get_cat_age(cat_details["mintedAt"])
    cat_bucket_idx = cat_number // 1000
    image_url = f"{CAT21_IMAGE_BASE_URL}/pngs/{cat_bucket_idx}/cat_{cat_number}.png"

    embed = discord.Embed(
        title=f"Cat #{cat_number}",
    )
    embed.set_image(url=image_url)
    embed.add_field(
        name="Age",
        value=cat_age,
        inline=True,
    )
    embed.add_field(
        name="Feerate",
        value=f"{cat_details['feeRate']:.1f} sat/vB [View Transaction](https://ordpool.space/tx/{cat_details["txHash"]})",
        inline=True,
    )
    await ctx.send(embed=embed)
    return


@bot.command()
async def minter(ctx, address: str):
    logging.info(f"!minter {address} from '{ctx.author.name}' ID {ctx.author.id}")

    try:
        minted_cats = await get_cats_by_minter(address)
    except aiohttp.client_exceptions.ClientResponseError:
        await ctx.send(f"No cats minted by address `{address}`, how is this possible? Time to mint some. Zoom zoom!")
        return
    except Exception:
        await ctx.send(
            "Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone else's back-end in the meantime."
        )
        logging.exception(f"Error fetching minted cats for address `{address}`")
        return

    embed = discord.Embed(
        title=f"Minted cats",
        description="Here's what I found!",
    )

    for cat in minted_cats:
        # Add each cat as a field with a link to the transaction
        embed.add_field(
            name=f"Cat #{cat["catNumber"]}",
            value=f"{cat['feeRate']:.1f} sat/vB [View Transaction](https://ordpool.space/tx/{cat["txHash"]})",
            inline=True
        )

    # Send the embed to Discord
    await ctx.send(embed=embed)


if __name__ == "__main__":
    # Run the bot
    bot.run(DISCORD_BOT_TOKEN)
