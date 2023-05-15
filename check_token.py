from tiktoken import Tokenizer, TokenCount
from typing import Tuple

def check_token_length(input_text: str, max_length: int) -> Tuple[bool, int]:
    # Initialize the tiktoken tokenizer
    tokenizer = Tokenizer()
    token_count = TokenCount()

    # Tokenize the input text and count the tokens
    for token in tokenizer.tokenize(input_text):
        token_count.add(token)

    # Get the tokenized length
    tokenized_length = token_count.total()

    # Check if the tokenized length exceeds the maximum length
    if_exceed = tokenized_length > max_length

    return if_exceed, tokenized_length
