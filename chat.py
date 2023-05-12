import json
import clipboard
import argparse
import os
from pdf_parser import ContextNode
from api import Message, send_messages

SYSTEM_PROMPT = """
As an AI, you provide answers to questions based on JSON-formatted documents. Follow these steps:
1. User provides a JSON string of summarized document contexts.
2. User asks a question.
3. For general questions, answer using your own knowledge, considering the context.
4. For document-specific questions, locate the relevant part of the document. Hint: if you don't know where to look at, guess one.
5. If the summarized context is insufficient, request more details:
   {"response_type": "request", "targets": [<node_ids>], "original": true/false}
   Choose "original" based on whether you need the original or summarized version.
6. Once you have the necessary information, answer like this:
   {"response_type": "answer", "content": "<answer>", "references": ["<node_id>", ...]}
7. Use double quotes for keys and values in JSON strings. Reply only with JSON strings.
8. If your request is invalid, or you can't find the answer, request the "root" node_id or a different one.
9. If you need the user to clarify the question, use "answer" as the response_type and request clarification.

Reminders:
- Avoid requesting previously requested node_ids. If you can't find the answer, request a different node_id or ask for clarification.
- Pay close attention to the context tree. A node may have completely different contexts from another node on the same level.
- Pay close attention to the previous questions. The user may be asking questions based on previous conversations.
- Answer with as many details as possible, unless otherwise specified.

Example:
Context: {...}
Previous Requests: ["2"]
Question: What is the thread model introduced in the paper?
Assistant: {"response_type": "request", "targets": ["3"], "original": true}
"""

class ContextChatBot:
    def __init__(self, root_node: ContextNode, curr_question: str = "", clipboard_mode: bool = False):
        self.root_node = root_node
        self.history = [Message("system", SYSTEM_PROMPT)]
        self.curr_question = curr_question
        self.current_contexts = str(self.root_node.get_context(1))
        self.clipboard_mode = clipboard_mode
        self.previous_requests = []

    def load_contexts(self, file_path: str):
        with open(file_path, "r") as f:
            json_string = f.read()
        self.root_node = ContextNode.from_json(json_string)

    def pop_history(self, n: int = 1):
        self.history = self.history[:1] + self.history[1+n:]

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
        previous_requests_prompt = f"Previous Requests: {self.previous_requests}\n"
        json_reminder = "Remember to output a valid JSON string.\n"
        return Message("user", context_prompt + previous_requests_prompt + question_prompt + json_reminder)

    def process_response(self, response_content: str):
        response_content = self.extract_json(response_content)
        print(f"Raw response: {response_content}")

        response, is_json = self.load_json(response_content)
        if not is_json:
            return response_content, []

        if response['response_type'] == 'request':
            self.previous_requests += response['targets']
            return self.handle_request_response(response)
        elif response['response_type'] == 'answer':
            self.previous_requests = []
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
        if len(self.history) >= 6:
            self.pop_history(2)
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
    parser.add_argument('--read-json', '-r', nargs='+', required=True, help="Path to one or more JSON files with context data")
    parser.add_argument('--clipboard-mode', '-c', action='store_true', help="Enable clipboard mode")

    args = parser.parse_args()

    root_node = ContextNode("root")
    if len(args.read_json) == 1:
        if not os.path.isfile(args.read_json[0]):
            print(f"Error: File {args.read_json[0]} does not exist.")
            return
        if not is_valid_json(args.read_json[0]):
            print(f"Error: {args.read_json[0]} is not a valid JSON file.")
            return
        with open(args.read_json[0], "r") as f:
            json_string = f.read()
        root_node = ContextNode.from_json(json_string)
    else:
        for json_file in args.read_json:
            if not os.path.isfile(json_file):
                print(f"Error: File {json_file} does not exist.")
                return
            if not is_valid_json(json_file):
                print(f"Error: {json_file} is not a valid JSON file.")
                return
            with open(json_file, "r") as f:
                json_string = f.read()
            root_node.add_child(ContextNode.from_json(json_string))
    
    print(f"Context data loaded:\n{str(root_node.to_dict())}")

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