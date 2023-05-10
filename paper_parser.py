import PyPDF2
import json
import argparse
from tqdm import tqdm
from llm_compressor import compress

class DocumentNode:
    """
    A node of a paper
    """
    def __init__(self, node_id: str, title: str = "", content: str = "", summary: str = "", word_limit: int = 2000):
        self.node_id = node_id
        self.title = title
        self.content = content
        self.children = []
        self.summary = summary
        self.word_limit = word_limit

    def add_child(self, child):
        self.children.append(child)

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "children": [child.to_dict() for child in self.children],
            "word_limit": self.word_limit
        }

    def to_json(self, indent=None):
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_dict(cls, data):
        node = cls(
            node_id=data.get("node_id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            word_limit=data.get("word_limit", 2000)
        )
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            node.add_child(child)
        return node

    def to_json(self, indent=None):
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_json(cls, json_string):
        data = json.loads(json_string)
        return cls.from_dict(data)
    
    def apply_word_limit(self):
        """
        Apply the word limit to the content of the node and its children
        If the content of the node is longer than the word limit, the content will be split into chunks
        Chunks are ending with complete sentences, and appended to the children of the node
        """
        if len(self.children) > 0:
            for child in self.children:
                child.apply_word_limit()
        if len(self.content.split(" ")) <= self.word_limit:
            return
        # Split the content into sentences
        sentences = self.content.split(". ")
        words_in_sentences = [len(sentence.split(" ")) for sentence in sentences]
        chunks = []
        current_chunk = ""
        for i, sentence in enumerate(sentences):
            if len(current_chunk.split(" ")) + words_in_sentences[i] > self.word_limit:
                chunks.append(current_chunk)
                current_chunk = ""
            current_chunk += sentence + ". "
        chunks.append(current_chunk)
        self.content = ""
        for i, chunk in enumerate(chunks):
            self.add_child(DocumentNode(f"{self.node_id}_c{i}", "", chunk, "", self.word_limit))
    
    def get_node(self, node_id):
        if self.node_id == node_id:
            return self
        for child in self.children:
            found_node = child.get_node(node_id)
            if found_node is not None:
                return found_node
        return None
    
    def get_id_list(self):
        id_list = [self.node_id]
        for child in self.children:
            id_list += child.get_id_list()
        return id_list

    def generate_summary(self, recursive: bool = True, compression_ratio: str = "1/4"):
        """
        Generate the summary of the node and its children
        """
        if len(self.children) > 0 and recursive:
            for child in self.children:
                child.generate_summary()
        children_summaries = [child.summary for child in self.children]
        if self.node_id == "references&appendix":
            return
        print(f"Generating summary for {self.node_id}")
        self.summary = compress(self.content + "\n".join(children_summaries), compression_ratio)
        print(f"Summary length: {len(self.summary.split(' '))} words")
        # TODO: Check if compress input is too long
    
    def get_summary(self, depth: int = 0):
        """
        Get the summary of the node and its children
        """
        summary = ""
        summary += self.summary + "\n"
        if depth <= 0:
            return summary
        for child in self.children:
            summary += child.get_summary(depth - 1)
        return summary

def extract_text_from_pdf(file_path):
    with open(file_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in tqdm(pdf_reader.pages, desc="Extracting text"):
            text += page.extract_text()
    return text

def parse_nodes(file_path):
    text = extract_text_from_pdf(file_path)
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
    root_node = DocumentNode("root", "Root", "")
    abstract_node = DocumentNode("abstract", "Abstract", "\n".join(lines[abstract_start + 1:abstract_end]).strip())
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
        current_node = DocumentNode(".".join(map(str, current_code)), node_title, node_content)

        # Determine the parent of the current node
        while current_parent.node_id != "root" and len(current_node.node_id) <= len(current_parent.node_id):
            current_parent = current_parent.parent if current_parent.parent else root_node

        current_node.parent = current_parent
        current_parent.add_child(current_node)
        current_parent = current_node

    # Add references node
    references_node = DocumentNode("references&appendix", "References", "\n".join(lines[reference_start + 1:]).strip())
    root_node.add_child(references_node)

    return root_node

def main():
    parser = argparse.ArgumentParser(description="Generate summaries from PDF files")
    parser.add_argument("-i", "--input", type=str, help="The PDF file to generate summaries from")
    parser.add_argument("--compression-ratio", type=str, default="1/4", help="The compression ratio to use")
    parser.add_argument("-o", "--output", type=str, default="summary.json", help="The output json file")
    args = parser.parse_args()

    root_node = parse_nodes(args.input)
    root_node.generate_summary(args.compression_ratio)
    with open(args.output, "w") as file:
        file.write(root_node.to_json())

if __name__ == "__main__":
    main()
