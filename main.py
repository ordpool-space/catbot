import os
import sys
import discord
import requests
import logging
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


async def get_status():
    res = requests.get(CAT21_API_URL + "/api/status")
    res.raise_for_status()
    return res.json()


async def get_cat_details(cat_number: int) -> dict:
    res = requests.get(CAT21_API_URL + f"/api/cat/by-num/{cat_number}")
    res.raise_for_status()
    return res.json()


def get_cat_age(minted_at: str) -> str:
    tdelta = datetime.now() - datetime.strptime(minted_at, "%Y-%m-%dT%H:%M:%S+00:00")
    return f"{tdelta.days} days (born {minted_at})"


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def cat(ctx, identifier: str):
    logging.info(f"Received !cat command with identifier {identifier}")

    if not identifier.isdigit() or int(identifier) < 0:
        await ctx.send(f"My cats are identified by numbers, please try again.")
        return

    cat_number = int(identifier)

    try:
        status = await get_status()
    except Exception as e:
        await ctx.send(
            f"Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone elses back-end in the meantime."
        )
        logging.exception(f"Unable to call get_status")
        return

    if cat_number > status["indexedCats"]:
        await ctx.send(
            f"Cat {cat_number} unknown to me. If it's newly minted, ping @ethspresso to update me about it."
        )
        return

    try:
        cat_details = await get_cat_details(cat_number)
    except Exception as e:
        await ctx.send(
            f"Uh-oh, I'm not able to reach my back-end. Maybe I'll chase someone elses back-end in the meantime."
        )
        logging.exception(f"Unable to call get_cat_details")
        return

    cat_age = get_cat_age(cat_details["mintedAt"])

    embed = discord.Embed(
        title=f"Cat #{cat_number}"
    )
    embed.add_field(
        name="Age",
        value=cat_age,
        inline=False,
    )
    embed.add_field(
        name="Feerate",
        value=f"{cat_details['feeRate']} sat/vB",
        inline=False
    )
    embed.add_field(
        name="Minter",
        value=cat_details["mintedBy"],
        inline=False
    )
    embed.add_field(
        name="Transaction",
        value=f"https://ordpool.space/tx/{cat_details['txHash']}",
        inline=False
    )
    await ctx.send(embed=embed)
    return


if __name__ == "__main__":
    # Run the bot
    bot.run(DISCORD_BOT_TOKEN)
