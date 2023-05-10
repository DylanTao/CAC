import openai
import json
from typing import List

SYSTEM_PROMPT = """
You will be given a long text in triple single quotes.
- User will specify the compression ratio and maximum word count. Try to compress the text to the specified ratio without exceeding the maximum word count.
- The compressed text should maintain the original meaning, tense, tone, and structure.
- The compressed text should be one paragraph.
"""

class Message:
    def __init__(self, role, content):
        self.role = role
        self.content = content
    
    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content
        }

def send_messages(messages: List[Message]) -> Message:
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[message.to_dict() for message in messages],
            temperature=0.1
        )
        response_message = Message(completion['choices'][0]['message']['role'],completion['choices'][0]['message']['content'])
        return response_message

    except Exception as e:
        print("Error: ", e)
        return None

def compress(text, compression_ratio: str = "1/4", max_words: int = "150"):
    system_messages = [Message("system", SYSTEM_PROMPT)]
    user_prompt = ""
    user_prompt += f"Compression ratio: {compression_ratio}\n"
    user_prompt += f"Maximum word count: {max_words}\n"
    user_prompt += f"Text: '''{text}'''\n"
    user_messages = [
        Message("user", user_prompt),
    ]
    messages = system_messages + user_messages
    response_message = send_messages(messages)
    return response_message.content
