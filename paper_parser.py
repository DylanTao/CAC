import PyPDF2

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
        next_sections.append([current_section[0] + 1])
        next_sections.append(current_section[:-1] + [current_section[-1] + 1])
        next_sections.append(current_section + [1])
        return next_sections
    
    def is_next_valid_section(current_section, next_section):
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
            section_code = list(map(int, first_word.split(".")))
            section_candidates.append({"code": section_code, "line": i})
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
                section_code = list(map(int, first_word.split(".")))
                section_candidates.remove(next(c for c in section_candidates if c["code"] == section_code))
    
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
    sections["abstract"] = {
        "title": "Abstract",
        "content": "\n".join(lines[abstract_start + 1:abstract_end]).strip()
    }
    
    for i, candidate in enumerate(section_candidates):
        if candidate["line"] < selected_section_candidates[-1]["line"]:
            continue
        current_section = candidate["code"]
        remaining_sections = [c["code"] for c in section_candidates[i + 1:]]
        scores = []
        for remaining_section in remaining_sections:
            scores.append(is_next_valid_section(remaining_section, current_section))
        if sum(scores) == 0:
            continue
        best_score_index = scores.index(max(scores)) + i + 1
        selected_section_candidates.append(section_candidates[best_score_index])

    for i, candidate in enumerate(selected_section_candidates):
        current_code = candidate["code"]
        title = lines[candidate["line"]].strip()
        if i < len(selected_section_candidates) - 1:
            # If there's a next match, use its line number as the end index for the current section
            end_index = selected_section_candidates[i + 1]["line"]
        else:
            # If this is the last match, use the end of the text as the end index
            end_index = reference_start

        section_content = "\n".join(lines[candidate["line"] + 1:end_index]).strip()
        sections[".".join(map(str, current_code))] = {
            "title": title,
            "content": section_content
        }

    sections["references"] = {
        "title": "References",
        "content": "\n".join(lines[reference_start + 1:]).strip()
    }

    return sections


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
