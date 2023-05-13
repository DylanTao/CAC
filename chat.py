import json
import clipboard
import argparse
import os
from encoder import ContextNode
from api import Message, send_messages
from typing import Tuple, List

SYSTEM_PROMPT = """
As an AI, you provide answers to questions based on JSON-formatted documents. Follow these steps:
1. User provides a JSON string of summarized document contexts.
2. User asks a question or makes a statement. If you believe user is not seeking an answer about the document, behave like a normal chatbot, answer with response_type "answer".
3. Consider the context and your own knowledge to generate a response. Don't just look for explicit answers, but also try to infer and reason based on the information given.
4. For document-specific questions, locate the relevant part of the document. Guess one if you don't know where to look.
5. If the summarized context is insufficient, request more details:
   {"response_type": "request", "targets": [<node_ids>], "reasoning": "<reasoning>", "original": true/false}
   Choose "original" based on whether you need the original or summarized version.
   node_ids are a list of ids found in the context tree and not in the previous requests. You should never request for "root".
   For reasoning, explain what the user needs, and why you need more details in the request targets, and how you will use the information.
6. Once you have the necessary information, answer like this:
   {"response_type": "answer", "content": "<answer>", "reasoning":"<reasoning>", "references": ["<node_id>", ...]}
   For reasoning, explain how you used the information provided in the context to generate the answer.
7. Use double quotes for keys and values in JSON strings. Reply only with JSON strings.
8. If your cannot find the answer, and you believe that without more information, you should always try requesting for details first before asking user for clarification.

Reminders:
- NEVER request previously requested node_ids. If you can't find the answer, request a different node_id or ask for clarification.
- Pay close attention to the context tree. A node may have completely different contexts from another node on the same level.
- Pay close attention to the previous questions. The user may be asking questions based on previous conversations.
- Answer with as many details as possible, unless otherwise specified.
- Understand and interpret the content of the documents. Don't just look for explicit text matches but also consider information that's implied or can be inferred.
- Use the context to its fullest extent, including making inferences and drawing conclusions based on the available information. This can include inferring the author's intentions, comparing and contrasting ideas, summarizing key points, or compose new contents, etc.
- The answer may not be explicitly stated in the document. Use your knowledge and understanding to reason and generate a meaningful response.
- Use bullet points or tables to list items, use **bold** to highlight important points, use *italics* to refer to specific terms.
- User may interact you in a conversational manner. You should be able to understand and respond to the user's questions and statements.

Example:
Context: {...}
Previous Requests: ["root", "doc.1", "doc.2"]
Question: What is the threat model introduced in the paper?
Assistant: {"response_type": "request", "targets": ["doc.3"], "reasoning": "User is asking for the threat model in the paper. doc.3 has title Threat Model, and is not in previous requests. I should be able to find details about the threat model in the original text in this node.", "original": true}

Example:
Context: {...}
Previous Requests: ["root", "doc.1", "doc.2", "doc.3"]
Question: What is the threat model introduced in the paper?
Assistant: {"response_type": "answer", "content": "The threat model introduced in the paper is ...", "reasoning": "I found the answer in the original text in doc.3. I used the information provided in the context to generate the answer.", "references": ["doc.3"]}
"""

class ContextChatBot:
    def __init__(self, root_node: ContextNode, curr_question: str = "", clipboard_mode: bool = False):
        self.root_node = root_node
        self.history = [Message("system", SYSTEM_PROMPT)]
        self.curr_question = curr_question
        self.current_contexts = str(self.root_node.get_context(1))
        self.clipboard_mode = clipboard_mode
        self.previous_requests = ["root"]

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
            # input("Press enter to continue")
            clipboard.copy(user_message.content)
            response_content = input("Please paste the AI response:\n")
        else:
            # input("Press enter to continue")
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

    def process_response(self, response_content: str) -> Tuple[str, str, List[str]]:
        response_content = self.extract_json(response_content)
        print(f"Raw response: {response_content}")

        response, is_json = self.load_json(response_content)
        if not is_json:
            return response_content, "", []

        if response['response_type'] == 'request':
            for target in response['targets']:
                if target in self.previous_requests:
                    response['targets'].remove(target)
            return self.handle_request_response(response)
        elif response['response_type'] == 'answer':
            self.previous_requests = ["root"]
            return self.handle_answer_response(response)
        else:
            print("Invalid response type")
            return response_content, "", []

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
        original = False
        if "original" in response.keys():
            original = response["original"]
        nodes, contexts = self.get_nodes_and_contexts(node_ids, original)

        if nodes:
            self.history.append(Message("assistant", str(response)))
            self.previous_requests += response['targets']
            return self.ask(self.curr_question, contexts)
        else:
            return self.ask("Request is invalid. Try to request for a valid id." + self.curr_question, self.current_contexts)

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

    def handle_answer_response(self, response: dict) -> Tuple[str, str, List[str]]:
        answer = response['content']
        reasoning = response['reasoning']
        references = response.get('references', [])
        return answer, reasoning, references

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
        answer, reasoning, references = chatbot.ask(question)
        print(f"Assistant\n> {answer}\n")
        if references:
            print(f"References: {references}\n")
        if reasoning:
            print(f"Reasoning: {reasoning}\n")

def is_valid_json(file_path: str) -> bool:
    try:
        with open(file_path, "r") as f:
            json.load(f)
        return True
    except Exception as e:
        return False

if __name__ == "__main__":
    main()