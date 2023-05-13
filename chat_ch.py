import json
import clipboard
import argparse
import os
from encoder import ContextNode
from api import Message, send_messages

SYSTEM_PROMPT = """
作为AI，您根据JSON格式的文件提供问题的答案。请按照以下步骤操作：
1. 用户提供了一个JSON字符串，包含概括的文件内容。
2. 用户提出一个问题。
3. 对于一般性的问题，使用您自己的知识进行回答，并考虑到上下文。
4. 对于特定文件的问题，找出文件的相关部分。提示：如果你不知道在哪里找，那就猜一个。
5. 如果概括的内容不足，要求提供更多的细节：
   {"response_type": "request", "targets": [<node_ids>], "original": true/false}
   根据你是否需要原始版本或概括版本选择 "original"。
6. 一旦你有了必要的信息，像这样回答：
   {"response_type": "answer", "content": "<answer>", "references": ["<node_id>", ...]}
7. 在JSON字符串中，键和值都用双引号。只用JSON字符串进行回复。
8. 如果你的请求无效，或者你找不到答案，请求 "root" node_id 或者其他的node_id。
9. 如果你需要用户澄清问题，使用 "answer" 作为 response_type 并请求澄清。

提醒:
- 记住避免请求先前请求过的node_ids。如果你找不到答案，请求另一个node_id或者要求澄清。
- 尤其注意上下文树，一个节点可能与同级的另一个节点有完全不同的上下文。
- 注意用户之前提到的问题，用户很可能在上一个问题的基础上提出新的问题。
- 回答应该包括尽可能多的细节，除非用户明确要求概括。

例如：
上下文: {...}
以前的请求: ["2"]
问题: 该论文介绍了哪种线程模型？
助手: {"response_type": "request", "targets": ["3"], "original": true}
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
        question_prompt = f"问题: {question}\n"
        previous_requests_prompt = f"以前的请求: {self.previous_requests}\n"
        context_prompt = f"上下文: {contexts}\n"
        json_reminder = "请记得使用JSON字符串进行回复。\n"
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