from typing import Tuple
from api import Message, send_messages
import nltk
from nltk import word_tokenize
from nltk.corpus import stopwords
from nltk.probability import FreqDist
from collections import Counter

nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nltk.download('stopwords')

# TODO: Use tiktoken to count the tokenized text length

SYSTEM_PROMPT = """
You will be given a long text in triple single quotes. Think about this step by step:
- User will specify the compression ratio and maximum word count.
- Generate a short summary of the text that is compressed to the specified compression ratio and 
maximum word count.
- The compressed text should maintain the original meaning, tense, tone, and structure.
- The compressed text should be one paragraph.
- Directly output the compressed text in triple single quotes.
Example:
User:
Compression ratio: 1/4
Maximum word count: 150
Text: '''Example text'''
Assistant:
'''Example compressed text'''
"""

def compress(text, compression_ratio: str = "1/4", max_words: int = "150"):
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
    if "'''" not in response_message.content:
        return response_message.content
    compressed_text = response_message.content.split("'''")[1]
    return compressed_text

def generate_title_and_summary(text: str, compression_ratio: str = "1/4", max_words: int = 150) -> Tuple[str, str]:
    # Generate the summary
    summary = compress(text, compression_ratio, max_words)

    # Tokenize the text
    tokens = word_tokenize(text.lower())
    # Remove stopwords and punctuation
    stop_words = set(stopwords.words("english"))
    filtered_tokens = [word for word in tokens if word.isalnum() and word not in stop_words]

    # Calculate word frequency and choose the top 3 keywords
    word_freq = FreqDist(filtered_tokens)
    top_keywords = [word for word, freq in word_freq.most_common(3)]

    # Generate the title
    title = f"{' '.join(top_keywords).title()}"

    return title, summary