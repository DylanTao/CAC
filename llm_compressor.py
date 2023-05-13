import json
from typing import Tuple
from api import Message, send_messages

# TODO: Use tiktoken to count the tokenized text length

SYSTEM_PROMPT = """
You will be given a long text in triple single quotes. Think about this step by step:
- User will specify the compression ratio and maximum word count, and describe the text.
- Generate a short title that describes the content of the text.
- Generate a short summary of the text that is compressed to the specified compression ratio and 
maximum word count.
- The summary must maintain the original meaning, tense, tone, and structure.
- The summary should be one paragraph.
- Use the description to think about what information is important and should be included in the summary.
- You MUST output your title and summary in JSON format.
Example:
User:
Description: A research paper on the topic of NLP.
Compression ratio: 1/4
Maximum word count: 150
Text: '''Example text'''
Assistant:
{"summary": "Example summary", "title": "Example title"}
"""

def compress(text, compression_ratio: str = "1/4", max_words: int = "200", desc: str = "document") -> Tuple[str, str]:
    system_messages = [Message("system", SYSTEM_PROMPT)]
    user_prompt = f"Description: {desc}\n"
    user_prompt += f"Compression ratio: {compression_ratio}\n"
    user_prompt += f"Maximum word count: {max_words}\n"
    user_prompt += f"Text: '''{text}'''\n"
    user_messages = [
        Message("user", user_prompt),
    ]
    messages = system_messages + user_messages
    response_message = send_messages(messages)
    if "{" not in response_message.content or "}" not in response_message.content:
        summary = response_message.content
        title = ""
    else:
        # Find the first { and last } to get the JSON
        response_json = json.loads(response_message.content[response_message.content.find("{"):response_message.content.rfind("}")+1])
        summary = response_json["summary"]
        title = response_json["title"]
    return title, summary