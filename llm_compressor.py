import json
from typing import Tuple
from api import Message, send_messages

# TODO: Use tiktoken to count the tokenized text length

SYSTEM_PROMPT = """
You will be given a long text in triple single quotes. Think about this step by step:
- User will specify the compression ratio and maximum word count.
- Generate a short title that describes the content of the text.
- Generate a short summary of the text that is compressed to the specified compression ratio and 
maximum word count.
- The summary must maintain the original meaning, tense, tone, and structure.
- The summary should be one paragraph.
- You MUST output your title and summary in JSON format.
Example:
User:
Compression ratio: 1/4
Maximum word count: 150
Text: '''Example text'''
Assistant:
{"summary": "Example summary", "title": "Example title"}
"""

def compress(text, compression_ratio: str = "1/4", max_words: int = "150") -> Tuple[str, str]:
    # Divide text into chunks if it is longer than 2000 words
    if len(text.split(" ")) >= 2000:
        chunks = []
        current_chunk = ""
        for sentence in text.split(". "):
            if len(current_chunk.split(" ")) + len(sentence.split(" ")) > 2000:
                chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += sentence + ". "
        chunks.append(current_chunk)
        # Compress each chunk
        compressed_chunks = []
        for chunk in chunks:
            compressed_chunks.append(compress(chunk, compression_ratio, max_words))
        # Compress all chunks into one
        return compress("\n".join(compressed_chunks), compression_ratio, max_words)
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
    if "{" not in response_message.content or "}" not in response_message.content:
        summary = response_message.content
        title = ""
    else:
        # Find the first { and last } to get the JSON
        response_json = json.loads(response_message.content[response_message.content.find("{"):response_message.content.rfind("}")+1])
        summary = response_json["summary"]
        title = response_json["title"]
    return title, summary