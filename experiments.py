import argparse
import asyncio
import logging

from agent import CatbotAgent
agent = CatbotAgent()

logging.basicConfig(level=logging.INFO, format="%(message)s")

async def main(question: str):
    async for answer in agent.process_question(question, "cli_user"):
        print('-' * 80)
        print(answer)
        print('-' * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask Catbot a question.")
    parser.add_argument("-q", "--question", required=True, type=str, help="The question you want to ask")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.question))
    except Exception as e:
        logging.exception("An error occurred while processing the question.")
