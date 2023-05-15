import tiktoken
from typing import Tuple

def check_token_length(input_text: str, max_token_length: int, model: str = "gpt-3.5-turbo") -> Tuple[bool, int]:
    # Initialize the tiktoken tokenizer
    encoding = tiktoken.get_encoding("cl100k_base")
    encoding = tiktoken.encoding_for_model(model)

    # Tokenize the input text and count the tokens
    token = encoding.encode(input_text)

    # Get the tokenized length
    tokenized_length = len(token)

    # Check if the tokenized length exceeds the maximum length
    if_valid = tokenized_length > max_token_length

    return if_valid, tokenized_length
