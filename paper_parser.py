import PyPDF2
import json

class Section:
    """
    A section of a paper
    """
    def __init__(self, section_id: str = "", title: str = "", content: str = "", summary: str = "", word_limit: int = 2000):
        self.section_id = section_id
        self.title = title
        self.content = content
        self.children = []
        self.summary = summary
        self.word_limit = word_limit

    def add_child(self, child):
        self.children.append(child)

    def to_dict(self):
        return {
            "section_id": self.section_id,
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
        section = cls(
            section_id=data.get("section_id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            word_limit=data.get("word_limit", 2000)
        )
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            section.add_child(child)
        return section

    def to_json(self, indent=None):
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_json(cls, json_string):
        data = json.loads(json_string)
        return cls.from_dict(data)
    
    def apply_word_limit(self):
        """
        Apply the word limit to the content of the section and its children
        If the content of the section is longer than the word limit, the content will be split into chunks
        Chunks are ending with complete sentences, and appended to the children of the section
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
            self.add_child(Section(f"{self.section_id}_c{i}", "", chunk, "", self.word_limit))
    
    def get_section(self, section_id):
        if self.section_id == section_id:
            return self
        for child in self.children:
            found_section = child.get_section(section_id)
            if found_section is not None:
                return found_section
        return None

def extract_text_from_pdf(file_path):
    with open(file_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text

def parse_sections(text):
    def get_next_valid_sections(current_section):
        next_sections = []
        for i in range(len(current_section)):
            next_sections.append(current_section[:i] + [current_section[i] + 1])
        next_sections.append(current_section + [1])
        return next_sections
    
    def next_valid_section_score(current_section, next_section):
        if current_section in get_next_valid_sections(next_section):
            return get_next_valid_sections(next_section).index(current_section) + 1
        return 0

    lines = text.split("\n")
    section_candidates = []
    selected_section_candidates = []
    sections = {}
    abstract_start = 0
    reference_start = 0
    has_contents = False
    contents_start = 0
    
    for i, line in enumerate(lines):
        first_word = line.split(" ")[0]
        if first_word.replace(".", "").isdigit() and first_word[-1] != ".":
            # Get section code
            section_id = list(map(int, first_word.split(".")))
            section_candidates.append({"code": section_id, "line": i})
        if first_word.lower().startswith("contents") or line.lower().startswith("table of contents") and not has_contents:
            has_contents = True
            contents_start = i
        # if first_word.lower().startswith("abstract") and abstract_start == 0:
        #     abstract_start = i

    
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
                # Get section code
                section_id = list(map(int, first_word.split(".")))
                section_candidates.remove(next(c for c in section_candidates if c["code"] == section_id))
    
    # Find the first candidate with code [1], remove all candidates before it
    for i, candidate in enumerate(section_candidates):
        if candidate["code"] == [1]:
            section_candidates = section_candidates[i:]
            selected_section_candidates.append(candidate)
            abstract_end = candidate["line"] - 1
            if has_contents:
                abstract_end = contents_start - 1
            break
    
    # Add abstract section
    root_section = Section(None, "Root", "")
    abstract_section = Section("abstract", "Abstract", "\n".join(lines[abstract_start + 1:abstract_end]).strip())
    root_section.add_child(abstract_section)
    
    for i, candidate in enumerate(section_candidates):
        if candidate["line"] < selected_section_candidates[-1]["line"]:
            continue
        current_section = candidate["code"]
        remaining_sections = [c["code"] for c in section_candidates[i + 1:]]
        scores = []
        for remaining_section in remaining_sections:
            scores.append(next_valid_section_score(remaining_section, current_section))
        if sum(scores) == 0:
            continue
        best_score_index = scores.index(max(scores)) + i + 1
        selected_section_candidates.append(section_candidates[best_score_index])

    current_parent = root_section
    for i, candidate in enumerate(selected_section_candidates):
        current_code = candidate["code"]
        if i < len(selected_section_candidates) - 1:
            end_index = selected_section_candidates[i + 1]["line"]
        else:
            end_index = reference_start

        section_title = lines[candidate["line"]].strip()
        section_content = "\n".join(lines[candidate["line"]:end_index]).strip()
        current_section = Section(".".join(map(str, current_code)), section_title, section_content)

        # Determine the parent of the current section
        while current_parent.section_id is not None and len(current_section.section_id) <= len(current_parent.section_id):
            current_parent = current_parent.parent if current_parent.parent else root_section

        current_section.parent = current_parent
        current_parent.add_child(current_section)
        current_parent = current_section

    # Add references section
    references_section = Section("references&appendix", "References", "\n".join(lines[reference_start + 1:]).strip())
    root_section.add_child(references_section)

    return root_section

def main():
    file_path = "data/ZLeaks.pdf"
    text = extract_text_from_pdf(file_path)
    sections = parse_sections(text)

    for section, data in sections.items():
        print(f"Section {section}: {data['title']}")
        print(data['content'])
        print("\n\n")
        input()


if __name__ == "__main__":
    main()
