import openai
from typing import List

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
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[message.to_dict() for message in messages],
        temperature=0.5
    )
    response_message = Message(completion['choices'][0]['message']['role'],completion['choices'][0]['message']['content'])
    return response_message