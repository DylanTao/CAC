import streamlit as st
import json
import clipboard
from chat import ContextChatBot, SYSTEM_PROMPT
from encoder import ContextNode, parse_unstructured, extract_text_from_pdf
import os

# Create an instance of the chatbot
chatbot = ContextChatBot(ContextNode("root"))

# Create a title and a subtitle
encoder_tab, context_tree_tab, chat_tab, history_tab = st.tabs(["Customize Encoder","Context Tree", "Chat", "History"])

# Side bar for file upload
def handle_json(file):
    data = json.load(file)
    return ContextNode.from_dict(data)

def handle_nonjson(file):
    if file.type == "text/plain":
        # copy txt to a temporary file
        file_name = file.name
        with open(file_name, "w") as f:
            f.write(file.getvalue().decode("utf-8"))
        root_node = parse_unstructured(file_name)
    else:  # assume file is a PDF
        # copy pdf to a temporary file
        file_name = file.name
        with open(file_name, "wb") as f:
            f.write(file.getbuffer())
        root_node = parse_unstructured(file_name)
    root_node.apply_word_limit()
    root_node.generate_summary(True, title=True)
    # delete temporary file
    os.remove(file_name)

    # save the root node to a json file
    with open(file_name + ".json", "w") as f:
        f.write(root_node.to_json())

    return root_node

with st.sidebar:
    files = st.file_uploader("Upload files", type=["json", "pdf", "txt"], accept_multiple_files=True)
    if files:
        for file in files:
            if file.type == "application/json":
                node = handle_json(file)
            elif file.type == "text/plain":
                node = handle_nonjson(file)
            else:  # assume file is a PDF
                node = handle_nonjson(file)
            
            if len(files) == 1:
                chatbot.root_node = node
                chatbot.root_node.node_id = "root"
            else:
                chatbot.root_node.add_child(node)
                
with encoder_tab:
    # Allow user to change root node id and title
    root_id = st.text_input("Document type", chatbot.root_node.node_id)
    root_title = st.text_input("Default prompt", chatbot.root_node.title)
    # if st.button("Update root node"):
    #     chatbot.root_node.node_id = root_id
    #     chatbot.root_node.title = root_title
    # # Download current context tree
    # st.download_button("Download this context tree", json.dumps(chatbot.root_node.to_dict(), indent=4), chatbot.root_node.node_id + ".json", "text/json")
    # st.json(chatbot.root_node.to_dict())

with context_tree_tab:
    # Allow user to change root node id and title
    root_id = st.text_input("Root node id", chatbot.root_node.node_id)
    root_title = st.text_input("Root node title", chatbot.root_node.title)
    if st.button("Update root node"):
        chatbot.root_node.node_id = root_id
        chatbot.root_node.title = root_title
    # Download current context tree
    st.download_button("Download this context tree", json.dumps(chatbot.root_node.to_dict(), indent=4), chatbot.root_node.node_id + ".json", "text/json")
    st.json(chatbot.root_node.to_dict())

history = []
with chat_tab:
    user_input = st.text_area("Question", "", height=200)
    submit = st.button("Ask Chatbot")
    if user_input.strip() != "" and submit:
        chatbot.current_contexts = chatbot.root_node.get_context(1)
        answer, reasoning, references = chatbot.ask(user_input)
        history.append(f"**Question:**\n\n{user_input}")
        history.append(f"**Answer:**\n\n{answer}")
        st.markdown(f"**Answer:**\n\n{answer}")
        st.markdown(f"**Reasoning:**\n\n{reasoning}")
        st.markdown(f"**References:**\n\n{references}")
        if len(history) >= 2:  # there is at least one question and one answer
            regenerate = st.button("Regenerate Response")
            if regenerate:
                # Here we call the regenerate_response method to regenerate the response
                chatbot.regenerate_response()
        with st.expander("Show context"):
            for ref in references:
                node = chatbot.root_node.get_node(ref)
                if node is not None:
                    st.json(node.get_context(1))
            
with history_tab:
    for message in history:
        st.markdown(message)
