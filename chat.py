import json
import clipboard
import argparse
import os
from pdf_parser import ContextNode
from api import Message, send_messages

SYSTEM_PROMPT = """
You are an AI designed to output answers to question based on some documents in JSON format.
Your answers should be as detailed as possible, unless otherwise specified.
You should actively ask for more details.
Think about this step by step:
1. User will provide a JSON string of the summarized contexts of each parts of the document.
2. User will ask a question
3. If the question is a general question not asking specifically about a part of the document,
you need to keep the context in mind and answer the question with your own knowledge.
4. You need to find the part of the document that answers the question if the question needs
to be answered with knowledge from the document.
5. If you believe the summarized version of document is not enough to answer the question,
you need to request for more details with in the following format:
    {"response_type": "request", "targets": [<node_ids>], "original": true/false}
where <node_ids> are a list of the node_ids in the JSON string. "original" is True if you need the
original version, False if you need the summarized version. You should request for the original
text if answer is not found in the summarized version.
Pay close attention to the keywords in the question to determine which node_ids to request.
6. Once you have the information you need, output the answer in the following format:
    {"response_type": "answer", "content": "<answer>", "references": ["<node_id>", ...]},
where <answer> is the answer to the question, and references is a list of any node_id that you used to answer the question.
7. Always use double quotes for keys and values in the JSON string. Always reply with JSON string only.
8. If user tells you request is invalid, or you cannot locate the answer in the context, it is
possible that you requested for the wrong context. Try requesting for the node_id "root" to get
the full context, then try requesting a different node_id.
9. If you want to ask user to explain the question, reply with response_type "answer" and content

Example:
Context: {...}
Question: What is the thread model introduced in the paper?
Assistant: {"response_type": "request", "targets": ["2"], "original": true}

Example:
Context: {...}
Question: What is the thread model introduced in the paper?
Assistant: {"response_type": "answer", "content": "The thread model introduced in the paper is ...", "references": ["1"]}
"""

class ContextChatBot:
    def __init__(self, root_node: ContextNode, curr_question: str = "", clipboard_mode: bool = False):
        self.root_node = root_node
        self.history = [Message("system", SYSTEM_PROMPT)]
        self.curr_question = curr_question
        self.current_contexts = str(self.root_node.get_context(1))
        self.clipboard_mode = clipboard_mode

    def load_contexts(self, file_path: str):
        with open(file_path, "r") as f:
            json_string = f.read()
        self.root_node = ContextNode.from_json(json_string)

    def pop_history(self):
        self.history = self.history[:1] + self.history[3:]

    def reset_history(self):
        self.history = [Message("system", SYSTEM_PROMPT)]

    def ask(self, question: str, contexts: str = ""):
        self.curr_question = question
        if contexts == "":
            contexts = self.current_contexts
        user_message = self.prepare_user_message(question, contexts)

        print(user_message.content)
        if self.clipboard_mode:
            print("The message has been copied to your clipboard")
            input("Press enter to continue")
            clipboard.copy(user_message.content)
            response_content = input("Please paste the AI response:\n")
        else:
            input("Press enter to continue")
            response_message = send_messages(self.history + [user_message])
            self.history += [Message("user", f"Question: {question}\n")] + [response_message]
            response_content = response_message.content

        return self.process_response(response_content)


    def prepare_user_message(self, question: str, contexts: str):
        question_prompt = f"Question: {question}\n"
        context_prompt = f"Contexts: {contexts}\n"
        json_reminder = "Remember to output a valid JSON string.\n"
        return Message("user", question_prompt + context_prompt + json_reminder)

    def process_response(self, response_content: str):
        response_content = self.extract_json(response_content)
        print(f"Raw response: {response_content}")

        response, is_json = self.load_json(response_content)
        if not is_json:
            return response_content, []

        if response['response_type'] == 'request':
            return self.handle_request_response(response)
        elif response['response_type'] == 'answer':
            return self.handle_answer_response(response)
        else:
            print("Invalid response type")
            return response_content, []

    # Additional helper methods
    def extract_json(self, content: str):
        start = content.find("{")
        end = content.rfind("}")
        return content[start:end+1]

    def load_json(self, content: str):
        try:
            response = json.loads(content)
            return response, True
        except Exception as e:
            return content, False

    def handle_request_response(self, response: dict):
        print(f"AI requesting node_id: {response['targets']}")
        node_ids = response['targets']
        nodes, contexts = self.get_nodes_and_contexts(node_ids, response["original"])

        if nodes:
            self.history.append(Message("assistant", str(response)))
            return self.ask(self.curr_question, contexts)
        else:
            return self.ask("Request is invalid", self.current_contexts)

    def get_nodes_and_contexts(self, node_ids: list, original: bool):
        nodes = []
        contexts = ""
        for node_id in node_ids:
            node = self.root_node.get_node(node_id)
            if node is None:
                print("Invalid node_id")
                continue
            nodes.append(node)

            print(f"Getting contexts for node_id: {node.node_id}")
            contexts += str(node.get_context(1, original)) + "\n"
        return nodes, contexts

    def handle_answer_response(self, response: dict):
        answer = response['content']
        references = response.get('references', [])
        return answer, references

def main():
    parser = argparse.ArgumentParser(description="Interact with ContextChatBot")
    parser.add_argument('--read-json', '-r', type=str, required=True, help="Path to the JSON file with context data")
    parser.add_argument('--clipboard-mode', '-c', action='store_true', help="Enable clipboard mode")

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
    chatbot = ContextChatBot(root_node, clipboard_mode=args.clipboard_mode)

    print("Type 'exit' to quit the application.")
    print(f"Clipboard mode: {args.clipboard_mode}")
    if args.clipboard_mode:
        print("Clipboard mode enabled. The AI response will be copied to your clipboard.")
        clipboard.copy(SYSTEM_PROMPT)
        input("Now, paste the first system prompt into the chatbot. Press enter to continue.")
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