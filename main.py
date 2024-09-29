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
    help_command=help_cmd
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


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        help_text="""I'm a bot and a cat and a catbot. Here's what I know:

`!cat 27` means I show you how cat 27 looks. Awesome right?
`!cat` means you just want more cats in your life. Meow!
`!minter <address>` means you minted a lot and wanna try to get all the cats in one spot. Not easy I know!
"""
        await ctx.send(help_text)
    else:
        pass


# !cat to display all we know about a single cat
@bot.command(
    name="cat",
    brief="See all about this awesome cat!",
    help="""See a specific cat by number, like !cat 27
Or a random cat with !cat when you're feeling lucky! Meow!""",
)
async def acat(ctx, number: str = ""):
    requester_info = f"'{ctx.author.name}' ({ctx.author.id})"
    guild_info = f"'{ctx.guild.name}' ({ctx.guild.id})" if ctx.guild else "DM"
    logging.info(f"!cat {number} from {requester_info} in {guild_info}")

    try:
        status = await get_status()
    except Exception:
        await ctx.send(BACKEND_UNREACHABLE_MSG)
        logging.exception("Unable to call get_status")
        return

    if number.isdigit() and int(number) >= 0:
        cat_number = int(number)
    else:
        cat_number = random.randint(0, status["indexedCats"] - 1)

    if cat_number > status["indexedCats"]:
        await ctx.send(
            f"Cat {cat_number} unknown to me. If it's newly minted, ping @ethspresso to update me about it."
        )
        return

    try:
        cat_details = await get_cat_details(cat_number)
    except Exception:
        await ctx.send(BACKEND_UNREACHABLE_MSG)
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


# !minter to list all cats minted by one address
@bot.command(
    name="minter",
    brief="All the cats minted by one address",
    usage="""[address]  I'll dig deep and find all the cats minted by this taproot address. Phew!"""
)
async def minter(ctx, address: str):
    requester_info = f"'{ctx.author.name}' ({ctx.author.id})"
    guild_info = f"'{ctx.guild.name}' ({ctx.guild.id})" if ctx.guild else "DM"
    logging.info(f"!minter {address} from {requester_info} in {guild_info}")

    try:
        minted_cats = await get_cats_by_minter(address)
    except aiohttp.client_exceptions.ClientResponseError:
        await ctx.send(f"No cats minted by address `{address}`, how is this possible? Time to mint some. Zoom zoom!")
        return
    except Exception:
        await ctx.send(BACKEND_UNREACHABLE_MSG)
        logging.exception(f"Error fetching minted cats for address `{address}`")
        return

    embed = discord.Embed(
        title="Minted cats",
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
