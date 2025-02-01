import asyncio
import logging
import os
import re
import aiohttp
import requests
import tweepy

from dotenv import load_dotenv
from io import BytesIO
from typing import Optional

from agent import process_question

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv()

class TwitterBot:
    def __init__(self):
        logger.info("Initializing Twitter bot...")
        self.client = tweepy.Client(
            bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
            consumer_key=os.getenv("TWITTER_API_KEY"),
            consumer_secret=os.getenv("TWITTER_API_SECRET"), 
            access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
            access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
            wait_on_rate_limit=True,
        )

        # We need to create an API v1.1 instance for media uploads
        auth = tweepy.OAuth1UserHandler(
            os.getenv("TWITTER_API_KEY"),
            os.getenv("TWITTER_API_SECRET"),
            os.getenv("TWITTER_ACCESS_TOKEN"),
            os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        )
        self.api = tweepy.API(auth)

        # Get bot's user ID
        self.bot_id = self.client.get_me().data.id
        self.bot_username = self.client.get_me().data.username
        logger.info(f"Bot initialized with ID: {self.bot_id} (@{self.bot_username})")
        
        # Load last mention ID from file
        self.last_mention_file = "/data/twitter/last_processed_mention_id.txt"
        self.last_mention_id = self._load_last_mention_id()
        logger.info(f"Loaded last_mention_id: {self.last_mention_id}")

    def _load_last_mention_id(self) -> Optional[int]:
        """Load the last processed mention ID from file."""
        try:
            os.makedirs(os.path.dirname(self.last_mention_file), exist_ok=True)
            if os.path.exists(self.last_mention_file):
                with open(self.last_mention_file, 'r') as f:
                    last_id = f.read().strip()
                    return int(last_id) if last_id else None
        except Exception as e:
            logger.exception(f"Error loading last mention ID from file")

        # Default to this starting point if file does not exist
        return 232417914878304257

    def _save_last_mention_id(self, mention_id: int):
        """Save the last processed mention ID to file."""
        try:
            with open(self.last_mention_file, 'w') as f:
                f.write(str(mention_id))
            logger.debug(f"Saved last_mention_id: {mention_id}")
        except Exception as e:
            logger.exception(f"Error saving last mention ID to disk")

    async def process_and_reply(self, tweet_id: int, user_id: str, question: str):
        logger.info(f"Processing question from user {user_id} (tweet {tweet_id}): {question}")
        try:
            reply_parts = []
            async for response in process_question(question, f"twitter_user_{user_id}"):
                reply_parts.append(response)

            # Combine parts and split into tweets
            full_reply = "\n".join(reply_parts)
            tweet_parts = self._split_into_tweets(full_reply)
            logger.info(f"Split response into {len(tweet_parts)} tweets")

            # Send reply as a thread
            previous_tweet_id = tweet_id
            for i, part in enumerate(tweet_parts, 1):
                logger.info(f"Sending reply part {i}/{len(tweet_parts)}")
                
                # Detect image URLs and upload them
                media_ids = []
                image_urls = re.findall(r'https://preview\.cat21\.space/pngs/[0-9]+/cat_[0-9]+\.png', part)
                for image_url in image_urls:
                    # Download the image
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as resp:
                            image_data = await resp.read()

                    # Upload the image to Twitter
                    media = self.client.media_upload(image_data)
                    media_ids.append(media.media_id)
                
                response = self.client.create_tweet(
                    text=part,
                    in_reply_to_tweet_id=previous_tweet_id,
                    media_ids=media_ids,
                )
                previous_tweet_id = response.data['id']
                logger.info(f"Posted tweet {response.data['id']}")

        except Exception as e:
            logger.exception(f"Error processing tweet {tweet_id}")

    def _split_into_tweets(self, text: str, max_length: int = 280) -> list[str]:
        """Split long text into multiple tweet-sized chunks."""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        words = text.split()
        current_part = ""
        
        for word in words:
            if len(current_part) + len(word) + 1 <= max_length:
                current_part += (" " + word if current_part else word)
            else:
                parts.append(current_part)
                current_part = word
        
        if current_part:
            parts.append(current_part)
            
        return parts

    def upload_media(self, image_path_or_url: str) -> Optional[str]:
        """Upload media and return the media ID."""
        try:
            # Handle both local files and URLs
            if image_path_or_url.startswith(('http://', 'https://')):
                response = requests.get(image_path_or_url)
                response.raise_for_status()
                image_data = BytesIO(response.content)
                media = self.api.media_upload(filename='image', file=image_data)
            else:
                media = self.api.media_upload(filename=image_path_or_url)
            
            return media.media_id_string
        except Exception as e:
            logger.exception(f"Failed to upload media")
            return None

    async def check_mentions(self):
        """Check for new mentions and process them."""
        logger.info("Checking for new mentions...")
        try:
            mentions = self.client.get_users_mentions(
                id=self.bot_id,
                since_id=self.last_mention_id,
                tweet_fields=['referenced_tweets', 'author_id'],
                user_fields=['username'],
                expansions=['author_id']
            )

            if not mentions.data:
                logger.info("No new mentions found")
                return

            # Create user lookup dict
            users = {user.id: user for user in mentions.includes['users']}

            logger.info(f"Found {len(mentions.data)} new mentions")
            for mention in mentions.data:
                author = users[mention.author_id]
                tweet_url = f"https://x.com/{author.username}/status/{mention.id}"
                logger.info(f"Processing mention: {tweet_url}")

                # Extract question from tweet
                question = mention.text
                # Remove bot's mention from the question
                question = question.replace(f"@{self.bot_username}", "").strip()
                logger.info(f"Processing mention {mention.id} from user {mention.author_id}")

                try:
                    await self.process_and_reply(mention.id, mention.author_id, question)
                except Exception as e:
                    logger.exception(f"Error processing mention {mention.id}")
                    continue

                # Only update last_mention_id after successful processing
                if not self.last_mention_id or mention.id > self.last_mention_id:
                    self.last_mention_id = mention.id
                    self._save_last_mention_id(mention.id)
                    logger.info(f"Updated last mention ID to {self.last_mention_id} and saved it")

        except Exception as e:
            logger.exception(f"Error checking mentions")

    async def check_replies(self):
        """Check for replies to bot's tweets and process them."""
        logger.info("Checking for replies to bot's tweets...")
        try:
            # Get bot's recent tweets
            tweets = self.client.get_users_tweets(self.bot_id)
            if not tweets.data:
                logger.info("No recent bot tweets found")
                return

            logger.info(f"Checking replies for {len(tweets.data)} recent bot tweets")
            for tweet in tweets.data:
                logger.info(f"Checking replies to tweet {tweet.id}")
                # Get replies to this tweet
                replies = self.client.search_recent_tweets(
                    query=f"conversation_id:{tweet.id}",
                    tweet_fields=['referenced_tweets', 'author_id'],
                    user_fields=['username'],
                    expansions=['author_id']
                )
                
                if not replies.data:
                    logger.info(f"No replies found for tweet {tweet.id}")
                    continue

                # Create user lookup dict
                users = {user.id: user for user in replies.includes['users']}

                logger.info(f"Found {len(replies.data)} replies to tweet {tweet.id}")
                for reply in replies.data:
                    # Skip bot's own replies
                    if reply.author_id == self.bot_id:
                        logger.debug(f"Skipping own reply {reply.id}")
                        continue
                    
                    author = users[reply.author_id]
                    tweet_url = f"https://x.com/{author.username}/status/{reply.id}"
                    logger.info(f"Processing reply: {tweet_url}")
                    question = reply.text.strip()
                    await self.process_and_reply(reply.id, reply.author_id, question)

        except Exception as e:
            logger.error(f"Error checking replies: {str(e)}")

async def run_bot():
    logger.info("Starting Twitter bot...")
    bot = TwitterBot()
    while True:
        try:
            await bot.check_mentions()
            # Deal with complexity of follow-up questions later
            #await bot.check_replies()
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")

        logger.info("Sleeping for 1 minute...")
        await asyncio.sleep(1 * 60)

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise