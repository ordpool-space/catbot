import argparse

from agent import agent

if __name__ == "__main__":
    # use argparse to get question from command line
    parser = argparse.ArgumentParser(description="Ask Catbot a question.")
    parser.add_argument("-q", "--question", required=True, type=str, help="The question you want to ask the catbot")
    args = parser.parse_args()

    res = agent.run_sync(args.question)
    print(res.data)
    print('-' * 80)
    for msg in res.all_messages():
        print(msg)
        print()
    print(f"Tokens spent: {res.usage()}")
