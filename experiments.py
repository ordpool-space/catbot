import argparse

from pydantic_ai.messages import TextPart, ToolCallPart

from agent import agent

if __name__ == "__main__":
    # use argparse to get question from command line
    parser = argparse.ArgumentParser(description="Ask Catbot a question.")
    parser.add_argument("-q", "--question", required=True, type=str, help="The question you want to ask the catbot")
    args = parser.parse_args()

    res = agent.run_sync(args.question)
    for msg in res.all_messages():
        for part in msg.parts:
            if type(part) == TextPart:
                print(part.content)
            elif type(part) == ToolCallPart:
                print(f"Call {part.tool_name}: {part.args.args_dict}")
                print()

    print('-' * 80)
    for msg in res.all_messages():
        print(msg)
        print()
    print(f"Tokens spent: {res.usage()}")
