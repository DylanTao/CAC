import argparse
import json
import os
from chat import ContextChatBot
from pdf_parser import ContextNode

def main():
    parser = argparse.ArgumentParser(description="Interact with ContextChatBot")
    parser.add_argument('--read-json', '-r', type=str, required=True, help="Path to the JSON file with context data")

    args = parser.parse_args()

    if not os.path.isfile(args.read_json):
        print(f"Error: File {args.read_json} does not exist.")
        return

    if not is_valid_json(args.read_json):
        print(f"Error: {args.read_json} is not a valid JSON file.")
        return

    with open(args.read_json, "r") as f:
        json_string = f.read()
    
    root_node = ContextNode.from_json(json_string)
    chatbot = ContextChatBot(root_node)

    print("Type 'exit' to quit the application.")
    while True:
        question = input("Enter your question\n> ")
        if question.lower() == 'exit':
            break
        answer, references = chatbot.ask(question)
        print(f"Assistant\n> {answer}\n")
        if references:
            print(f"References: {references}\n")

def is_valid_json(file_path: str) -> bool:
    try:
        with open(file_path, "r") as f:
            json.load(f)
        return True
    except Exception as e:
        return False

if __name__ == "__main__":
    main()