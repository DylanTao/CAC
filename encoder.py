import PyPDF2
import json
import argparse
import os
from gensim import corpora, models
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.corpus import stopwords
from tqdm import tqdm
from llm_compressor import compress
from typing import List

def preprocess_text(text) -> List[str]:
    # Tokenize, remove stopwords and non-alphabetical tokens
    stop_words = set(stopwords.words('english'))
    return [word for word in word_tokenize(text.lower()) if word.isalpha() and word not in stop_words]

def identify_topics(texts, num_topics):
    # Create a Gensim dictionary from the texts
    dictionary = corpora.Dictionary(texts)
    # Use the dictionary to prepare a DTM (Document Term Matrix)
    dtm = [dictionary.doc2bow(doc) for doc in texts]
    # Create an LDA model
    lda_model = models.LdaModel(dtm, num_topics=num_topics, id2word=dictionary, passes=2)
    # Get the dominant topic for each sentence
    topics = [max(lda_model[doc], key=lambda x: x[1])[0] for doc in dtm if lda_model[doc]]
    return topics

class TOCNode:
    def __init__(self, node_id: str, title: str, page_number: int):
        self.node_id = node_id
        self.title = title
        self.page_number = page_number
        self.children = []
    
    def add_child(self, child):
        self.children.append(child)
    
    def __repr__(self) -> str:
        return f"{self.title} (Page {self.page_number})"
    
    def display(self, level=0):
        print("  " * level + str(self))
        for child in self.children:
            child.display(level + 1)

class ContextNode:
    def __init__(self, node_id: str, title: str = "", content: str = "", summary: str = ""):
        self.node_id = node_id
        self.title = title
        self.content = content
        self.children = []
        self.summary = summary

    def add_child(self, child):
        self.children.append(child)

    def to_dict(self):
        return {
            "id": self.node_id,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "children": [child.to_dict() for child in self.children],
        }

    def to_json(self, indent=4):
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_dict(cls, data):
        node = cls(
            node_id=data.get("id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
        )
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            node.add_child(child)
        return node
    
    @classmethod
    def from_json(cls, json_string):
        data = json.loads(json_string)
        return cls.from_dict(data)
    
    def get_node(self, node_id):
        if self.node_id == node_id:
            return self
        for child in self.children:
            found_node = child.get_node(node_id)
            if found_node is not None:
                return found_node
        return None
    
    def get_id_list(self, depth: int = 1):
        id_list = [self.node_id]
        if depth < 0:
            return []
        for child in self.children:
            id_list += child.get_id_list()
        return id_list

    def generate_summary(self, recursive: bool = True, compression_ratio: str = "1/4", title: bool = False, desc: str = "document"):
        """
        Generate the summary of the node and its children
        """
        if len(self.children) > 0 and recursive:
            for child in self.children:
                child.generate_summary(recursive, compression_ratio, title)
        children_summaries = [child.summary for child in self.children]
        if "references&appendix" in self.node_id:
            return
        print(f"Generating summary for {self.node_id}")
        generated_title, summary = compress(self.content + "\n".join(children_summaries), compression_ratio, desc=desc)
        if title:
            self.title = generated_title
        self.summary = summary
        print(f"Title: {self.title}")
        print(f"Summary length: {len(self.summary.split(' '))} words")
    
    def get_context(self, depth: int = 0, original: bool = False):
        """
        Get the context of the node and its children
        """
        if depth > 0 and len(self.children) == 0:
            original = True
        if depth < 0:
            content = ""
            summary = ""
        else:
            content = self.content if original else ""
            summary = self.summary if not original else ""
        context = {
            "id": self.node_id,
            "title": self.title
        }
        if content != "":
            context["content"] = content
        if summary != "":
            context["summary"] = summary
        if self.children == []:
            return context
        context["children"] = []
        for child in self.children:
            context["children"].append(child.get_context(depth - 1, original=False))
        return context
    
    def prepend_node_id(self, node_id: str):
        if not self.node_id.startswith(node_id):
            self.node_id = node_id + "." + self.node_id
        for child in self.children:
            child.prepend_node_id(node_id)
    
    def apply_word_limit(self, limit: int = 2000, overlap: int = 100, recursive: bool = True):
        words = self.content.split()
        print(f"Word count for {self.node_id}: {len(words)}")
        if len(words) <= limit:
            return

        # Split content into chunks
        chunks = []
        while len(words) > limit:
            chunk = words[:limit]
            chunks.append(chunk)
            words = words[limit-overlap:]
        if len(words) > 0:
            chunks.append(words)
        print(f"Chunked {self.node_id} into {len(chunks)} chunks")
        # Assign chunked content to child nodes
        self.children = []
        for i, chunk in enumerate(chunks):
            node_id = f"{self.node_id}.chunk_{i+1}"
            node_title = f"Chunk {i+1}"
            node_content = " ".join(chunk)
            chunk_node = ContextNode(node_id, title=node_title, content=node_content)
            self.children.append(chunk_node)

        # Replace the original content with a string indicating that contents are chunked and in children
        self.content = f"Content is too long and is chunked into {len(chunks)} child nodes."

        # Recursively apply word limit to child nodes
        if recursive:
            for child in self.children:
                child.apply_word_limit(limit, overlap, recursive)
    
    def build_tree(self, num_topics: int = 0, max_tokens: int = 2000, recursive: bool = True):
        """
        Generate context tree for unstructured text. This will not preserve the original flow of the text.

        Args:
            num_topics (int, optional): Maximum number of topics on the first level. Defaults to 0.
            max_tokens (int, optional): Ideal maximum token size. Defaults to 2000.
        """
        print(f"Token count for {self.node_id}: {len(word_tokenize(self.content))}")
        text = self.content
        self.content = ""
        # Split text into sentences
        sentences = sent_tokenize(text)
        # Preprocess sentences
        texts = [preprocess_text(sentence) for sentence in sentences]
        if num_topics == 0:
            # Predict number of topics
            token_count = len(word_tokenize(text))
            num_topics = min(10, (token_count // max_tokens))
        # Identify topics
        topics = identify_topics(texts, num_topics)
        # Get the actual number of topics
        num_topics = len(set(topics))
        print("Number of topics:", num_topics)
        if num_topics == 1:
            self.content = text
            return
        for i, topic in enumerate(topics):
            topic_id = f"{self.node_id}.{topic + 1}"
            # Check if the topic node already exists, if not create it
            topic_node = next((child for child in self.children if child.node_id == topic_id), None)
            if not topic_node:
                topic_node = ContextNode(topic_id)
                self.add_child(topic_node)
            # Add the sentence node to the topic node
            sentence = sentences[i]
            topic_node.content += f" {sentence}"
        
        # Recursively build tree for child nodes
        if recursive:
            for child in self.children:
                token_count = len(word_tokenize(child.content))
                if token_count > max_tokens:
                    child.build_tree(0, max_tokens)

def extract_text_from_pdf(file_path):
    print(f"Extracting text from {file_path}")
    with open(file_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in tqdm(pdf_reader.pages, desc="Extracting text"):
            text += page.extract_text()
    return text

def parse_paper(file_path):
    text = extract_text_from_pdf(file_path)
    root_id = "".join(file_path.split("/")[-1].split(".")[0:-1]).replace(" ", "_")
    def get_next_valid_nodes(current_node):
        next_nodes = []
        for i in range(len(current_node)):
            next_nodes.append(current_node[:i] + [current_node[i] + 1])
        next_nodes.append(current_node + [1])
        return next_nodes
    
    def next_valid_node_score(current_node, next_node):
        if current_node in get_next_valid_nodes(next_node):
            return get_next_valid_nodes(next_node).index(current_node) + 1
        return 0

    lines = text.split("\n")
    node_candidates = []
    selected_node_candidates = []
    nodes = {}
    abstract_start = 0
    reference_start = 0
    has_contents = False
    contents_start = 0
    
    for i, line in enumerate(lines):
        first_word = line.split(" ")[0]
        if first_word.replace(".", "").isdigit() and first_word[-1] != ".":
            # Get node code
            node_id = list(map(int, first_word.split(".")))
            node_candidates.append({"code": node_id, "line": i})
        if first_word.lower().startswith("contents") or line.lower().startswith("table of contents") and not has_contents:
            has_contents = True
            contents_start = i
    
    # Find references from the end of the text
    for i, line in enumerate(lines[::-1]):
        if line.lower().startswith("references"):
            reference_start = len(lines) - i - 1
            break
    
    if has_contents:
        # Remove all candidates inside the table of contents
        for i, line in enumerate(lines[contents_start:]):
            if line.lower().startswith("references"):
                break
            first_word = line.split(" ")[0]
            if first_word.replace(".", "").isdigit() and first_word[-1] != ".":
                # Get node code
                node_id = list(map(int, first_word.split(".")))
                node_candidates.remove(next(c for c in node_candidates if c["code"] == node_id))
    
    # Find the first candidate with code [1], remove all candidates before it
    for i, candidate in enumerate(node_candidates):
        if candidate["code"] == [1]:
            node_candidates = node_candidates[i:]
            selected_node_candidates.append(candidate)
            abstract_end = candidate["line"] - 1
            if has_contents:
                abstract_end = contents_start - 1
            break
    
    # Add abstract node
    root_node = ContextNode(root_id, root_id, "")
    abstract_node = ContextNode("abstract", "Abstract", "\n".join(lines[abstract_start + 1:abstract_end]).strip())
    root_node.add_child(abstract_node)
    
    for i, candidate in enumerate(node_candidates):
        if candidate["line"] < selected_node_candidates[-1]["line"]:
            continue
        current_node = candidate["code"]
        remaining_nodes = [c["code"] for c in node_candidates[i + 1:]]
        scores = []
        for remaining_node in remaining_nodes:
            scores.append(next_valid_node_score(remaining_node, current_node))
        if sum(scores) == 0:
            continue
        best_score_index = scores.index(max(scores)) + i + 1
        selected_node_candidates.append(node_candidates[best_score_index])

    current_parent = root_node
    for i, candidate in enumerate(selected_node_candidates):
        current_code = candidate["code"]
        if i < len(selected_node_candidates) - 1:
            end_index = selected_node_candidates[i + 1]["line"]
        else:
            end_index = reference_start

        node_title = lines[candidate["line"]].strip()
        node_content = "\n".join(lines[candidate["line"]:end_index]).strip()
        current_node = ContextNode(".".join(map(str, current_code)), node_title, node_content)

        # Determine the parent of the current node
        while current_parent.node_id != root_id and len(current_node.node_id) <= len(current_parent.node_id):
            current_parent = current_parent.parent if current_parent.parent else root_node

        current_node.parent = current_parent
        current_parent.add_child(current_node)
        current_parent = current_node

    # Add references node
    references_node = ContextNode("references&appendix", "References", "\n".join(lines[reference_start + 1:]).strip())
    root_node.add_child(references_node)

    # Finally, prepend all node ids with the root id
    root_node.prepend_node_id(root_id)
    return root_node

def parse_unstructured(file_path: str):
    root_id = "".join(file_path.split("/")[-1].split(".")[0:-1]).replace(" ", "_")
    text = ""
    if file_path.endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    elif file_path.endswith(".txt"):
        with open(file_path, "r") as file:
            text = file.read()
    else:
        raise Exception("Unsupported file format")
    root_node = ContextNode(root_id, root_id, text)
    return root_node

def parse_by_page(file_path):
    root_id = "".join(file_path.split("/")[-1].split(".")[0:-1]).replace(" ", "_")
    with open(file_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        root_node = ContextNode(root_id, root_id, "")
        for i, page in tqdm(enumerate(pdf_reader.pages), total=len(pdf_reader.pages), desc="Processing pages"):
            text = page.extract_text()
            node_id = f"p{i + 1}"
            title = f"{i + 1}"
            content = text.strip()
            page_node = ContextNode(node_id, title, content)
            root_node.add_child(page_node)
    root_node.prepend_node_id(root_id)
    return root_node

def parse_by_TOC(file_path, contents_path):
    root_id = "".join(file_path.split("/")[-1].split(".")[0:-1]).replace(" ", "_")
    with open(file_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        root_node = ContextNode("root", "Root", "")
        with open(contents_path, "r") as contents_file:
            toc = json.load(contents_file)
            for i, page in tqdm(enumerate(pdf_reader.pages), total=len(pdf_reader.pages), desc="Processing pages"):
                text = page.extract_text()
                node_id = f"p_{i + 1}"
                title = f"{i + 1}"
                content = text.strip()
                page_node = ContextNode(node_id, title, content)
                root_node.add_child(page_node)
    return root_node

def main():
    parser = argparse.ArgumentParser(description="Generate summaries from PDF files")
    parser.add_argument("-i", "--input", type=str, help="The PDF file to generate summaries from")
    parser.add_argument("-c", "--compression-ratio", type=str, default="1/4", help="The compression ratio to use")
    parser.add_argument("-o", "--output", type=str, help="The output json file")
    parser.add_argument("-u", "--unstructured", action="store_true", help="Parse the PDF file as unstructured text")
    parser.add_argument("-t", "--toc", type=str, help="The table of contents of the PDF file in JSON formatj")
    parser.add_argument("-p", "--page", action="store_true", help="Parse the PDF file by page")
    parser.add_argument("-d", "--desc", type=str, help="The description of the file to help encoder generate better summaries")
    parser.add_argument("-m", "--max-word", type=int, default=200, help="The maximum number of words in the summary")
    args = parser.parse_args()

    # Check if input is directory
    if os.path.isdir(args.input):
        file_paths = [os.path.join(args.input, filename) for filename in os.listdir(args.input) if filename.endswith('.pdf') or filename.endswith('.txt')]
        file_paths = [f'"{fp}"' for fp in file_paths]  # Enclose file paths in double quotes
        print(file_paths)
    else:
        file_paths = [args.input]

    for file_path in file_paths:
        if args.unstructured:
            root_node = parse_unstructured(args.input)
            root_node.apply_word_limit()
            root_node.generate_summary(True, args.compression_ratio, True, args.desc)
        elif args.page:
            root_node = parse_by_page(args.input)
            root_node.apply_word_limit(args.max_word)
            root_node.generate_summary(True, args.compression_ratio, True, args.desc)
        else:
            root_node = parse_paper(args.input)
            root_node.apply_word_limit(args.max_word)
            root_node.generate_summary(True, args.compression_ratio, False, args.desc)

        # Create output file path
        if args.output is not None:
            if os.path.isdir(args.output):
                output_file_path = os.path.join(args.output, os.path.splitext(os.path.basename(file_path))[0] + '.json')
            else:
                output_file_path = args.output
        else:
            output_file_path = os.path.splitext(file_path)[0] + '.json'

        with open(output_file_path, "w") as file:
            file.write(root_node.to_json())

if __name__ == "__main__":
    main()
