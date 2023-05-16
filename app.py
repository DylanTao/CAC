import streamlit as st
import json
import clipboard
from chat import ContextChatBot, SYSTEM_PROMPT
from encoder import ContextNode

# Create an instance of the chatbot
chatbot = ContextChatBot(ContextNode("root"))

# Create a title and a subtitle
tabs = st.tabs(["Context Tree", "Chat", "History", "Clipboard Chat"])

# Side bar for file upload
with st.sidebar:
    files = st.file_uploader("Upload json files", type=["json"], accept_multiple_files=True)
    if files:
        if len(files) == 1:
            chatbot.root_node = ContextNode.from_dict(json.load(files[0]))
            chatbot.root_node.node_id = "root"
        else:
            for file in files:
                data = json.load(file)
                chatbot.root_node.add_child(ContextNode.from_dict(data))

with tabs[0]:
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
with tabs[1]:
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
            
with tabs[2]:
    for message in history:
        st.markdown(message)
