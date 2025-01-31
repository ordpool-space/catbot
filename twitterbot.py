import asyncio
import logging
import tweepy
import os
from typing import Optional

from agent import process_question

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class TwitterBot:
    def __init__(self):
        logger.info("Initializing Twitter bot...")
        self.client = tweepy.Client(
            bearer_token=os.environ.get("TWITTER_BEARER_TOKEN"),
            consumer_key=os.environ.get("TWITTER_API_KEY"),
            consumer_secret=os.environ.get("TWITTER_API_SECRET"), 
            access_token=os.environ.get("TWITTER_ACCESS_TOKEN"),
            access_token_secret=os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")
        )
        
        # Get bot's user ID
        self.bot_id = self.client.get_me().data.id
        self.bot_username = self.client.get_me().data.username
        logger.info(f"Bot initialized with ID: {self.bot_id} (@{self.bot_username})")
        self.last_mention_id: Optional[int] = None

    async def process_and_reply(self, tweet_id: int, user_id: str, question: str):
        logger.info(f"Processing question from user {user_id} (tweet {tweet_id}): {question}")
        try:
            reply_parts = []
            async for answer in process_question(question, f"twitter_user_{user_id}"):
                reply_parts.append(answer)
                logger.debug(f"Generated answer part: {answer[:100]}...")

            # Combine parts and split into tweets
            full_reply = "\n".join(reply_parts)
            tweet_parts = self._split_into_tweets(full_reply)
            logger.info(f"Split response into {len(tweet_parts)} tweets")

            # Send reply as a thread
            previous_tweet_id = tweet_id
            for i, part in enumerate(tweet_parts, 1):
                logger.info(f"Sending reply part {i}/{len(tweet_parts)}")
                response = self.client.create_tweet(
                    text=part,
                    in_reply_to_tweet_id=previous_tweet_id
                )
                previous_tweet_id = response.data['id']
                logger.info(f"Posted tweet {response.data['id']}")

        except Exception as e:
            logger.error(f"Error processing tweet {tweet_id}: {str(e)}")
            try:
                self.client.create_tweet(
                    text="Sorry, I encountered an error while processing your question. Please try again later.",
                    in_reply_to_tweet_id=tweet_id
                )
                logger.info(f"Posted error response to tweet {tweet_id}")
            except Exception as e2:
                logger.error(f"Failed to post error message: {str(e2)}")

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

                # Update last processed mention ID
                if not self.last_mention_id or mention.id > self.last_mention_id:
                    self.last_mention_id = mention.id
                    logger.info(f"Updated last_mention_id to {self.last_mention_id}")

                # Extract question from tweet
                question = mention.text
                # Remove bot's mention from the question
                question = question.replace(f"@{self.bot_username}", "").strip()
                logger.info(f"Processing mention {mention.id} from user {mention.author_id}")
                
                await self.process_and_reply(mention.id, mention.author_id, question)

        except Exception as e:
            logger.error(f"Error checking mentions: {str(e)}")

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
            await bot.check_replies()
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")

        logger.info("Sleeping for 15 minutes...")
        await asyncio.sleep(15 * 60)

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise