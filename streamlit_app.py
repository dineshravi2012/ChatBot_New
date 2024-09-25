import streamlit as st
from snowflake.core import Root  # Requires snowflake>=0.8.0
from snowflake.cortex import Complete
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark import Session
# from transformers import GPT2Tokenizer

# Global variable to hold the Snowpark session
snowpark_session = None

def get_snowflake_session():
    # Access credentials from Streamlit secrets
    snowflake_credentials = st.secrets["SF_Dinesh2012"]
    global snowpark_session
    if snowpark_session is None:
        # Create Snowpark session
        connection_parameters = {
            "account": snowflake_credentials["account"],
            "user": snowflake_credentials["user"],
            "password": snowflake_credentials["password"],
            "warehouse": snowflake_credentials["warehouse"],
            "database": snowflake_credentials["database"],
            "schema": snowflake_credentials["schema"]
        }
        snowpark_session = Session.builder.configs(connection_parameters).create()
    return snowpark_session 

MODELS = [
    "mistral-large",
    "snowflake-arctic",
    "llama3-70b",
    "llama3-8b",
]

def init_session_state():
    """Initialize session state variables."""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'clear_conversation' not in st.session_state:
        st.session_state.clear_conversation = False
    if 'model_name' not in st.session_state:
        st.session_state.model_name = 'mistral-large'  # Change this to your model name

def init_messages():
    """Initialize the session state for chat messages."""
    if st.session_state.clear_conversation:
        st.session_state.messages = []  # Clear chat history
        st.session_state.clear_conversation = False  # Reset the flag

def init_service_metadata():
    """Initialize cortex search service metadata."""
    if "service_metadata" not in st.session_state:
        services = snowpark_session.sql("SHOW CORTEX SEARCH SERVICES;").collect()
        service_metadata = []
        if services:
            for s in services:
                svc_name = s["name"]
                svc_search_col = snowpark_session.sql(f"DESC CORTEX SEARCH SERVICE {svc_name};").collect()[0]["search_column"]
                service_metadata.append({"name": svc_name, "search_column": svc_search_col})
        st.session_state.service_metadata = service_metadata
    if not st.session_state.service_metadata:
        st.error("No Cortex search services found.")

def init_config_options():
    """Initialize configuration options in the sidebar."""
    st.sidebar.selectbox(
        "Select cortex search service:",
        [s["name"] for s in st.session_state.service_metadata],
        key="selected_cortex_search_service",
    )
    
    if st.sidebar.button("Clear conversation"):
        st.session_state.clear_conversation = True  # Set flag to True
        st.success("Conversation cleared!")

    st.sidebar.toggle("Debug", key="debug", value=False)
   # Comment out the toggle for chat history
   # st.sidebar.toggle("Use chat history", key="use_chat_history", value=False)

    with st.sidebar.expander("Advanced options"):
        st.selectbox("Select model:", MODELS, key="model_name")
        st.number_input(
            "Select number of context chunks",
            value=5,
            key="num_retrieved_chunks",
            min_value=1,
            max_value=10,
        )
        st.number_input(
            "Select number of messages to use in chat history",
            value=5,
            key="num_chat_messages",
            min_value=1,
            max_value=10,
        )

    st.sidebar.expander("Session State").write(st.session_state)

def query_cortex_search_service(query, columns=[], filter={}):
    """Query the selected cortex search service."""
    db, schema = snowpark_session.get_current_database(), snowpark_session.get_current_schema()

    cortex_search_service = (
        root.databases[db]
        .schemas[schema]
        .cortex_search_services[st.session_state.selected_cortex_search_service]
    )

    context_documents = cortex_search_service.search(
        query, columns=columns, filter=filter, limit=st.session_state.num_retrieved_chunks
    )
    results = context_documents.results

    service_metadata = st.session_state.service_metadata
    search_col = [s["search_column"] for s in service_metadata if s["name"] == st.session_state.selected_cortex_search_service][0].lower()

    context_str = ""
    for i, r in enumerate(results):
        context_str += f"Context document {i+1}: {r[search_col]} \n" + "\n"

    if st.session_state.debug:
        st.sidebar.text_area("Context documents", context_str, height=500)

    return context_str, results

def get_chat_history():
    """Retrieve the chat history from session state."""
    start_index = max(0, len(st.session_state.messages) - st.session_state.num_chat_messages)
    return st.session_state.messages[start_index:]

def complete(model, prompt):
    """Generate a completion using the specified model."""
    return Complete(model, prompt, session=snowpark_session).replace("$", "\$")

def make_chat_history_summary(chat_history, question):
    """Generate a summary of the chat history combined with the current question."""
    prompt = f"""
        [INST]
        Based on the chat history below and the question, generate a query that extends the question
        with the chat history provided. The query should be in natural language.
        Answer with only the query. Do not add any explanation.

        <chat_history>
        {chat_history}
        </chat_history>
        <question>
        {question}
        </question>
        [/INST]
    """
    summary = complete(st.session_state.model_name, prompt)

    if st.session_state.debug:
        st.sidebar.text_area("Chat history summary", summary.replace("$", "\$"), height=150)

    return summary

def create_prompt(user_question):
    """Create a prompt for the language model."""
    if st.session_state.use_chat_history:
        chat_history = get_chat_history()
        if chat_history:
            question_summary = make_chat_history_summary(chat_history, user_question)
            prompt_context, results = query_cortex_search_service(
                question_summary,
                columns=["chunk", "file_url", "relative_path"],
                filter={"@and": [{"@eq": {"language": "English"}}]},
            )
        else:
            prompt_context, results = query_cortex_search_service(
                user_question,
                columns=["chunk", "file_url", "relative_path"],
                filter={"@and": [{"@eq": {"language": "English"}}]},
            )
    else:
        prompt_context, results = query_cortex_search_service(
            user_question,
            columns=["chunk", "file_url", "relative_path"],
            filter={"@and": [{"@eq": {"language": "English"}}]},
        )

    prompt = f"""
            [INST]
            You are a helpful AI chat assistant with RAG capabilities. When a user asks you a question,
            you will also be given context provided between <context> and </context> tags. Use that context
            with the user's chat history provided between <chat_history> and </chat_history> tags
            to provide a summary that addresses the user's question. Ensure the answer is coherent, concise,
            and directly relevant to the user's question.

            If the user asks a generic question which cannot be answered with the given context or chat_history,
            just say "I don't know the answer to that question."

            Don't say things like "according to the provided context."

            <chat_history>
            {get_chat_history()}
            </chat_history>
            <context>
            {prompt_context}
            </context>
            <question>
            {user_question}
            </question>
            [/INST]
            Answer:
            """
    return prompt, results

def main():
    st.title(":speech_balloon: AI-Powered Chatbot for Document Querying")

    init_session_state()
    init_service_metadata()
    init_config_options()
    init_messages()

    icons = {"assistant": "❄️", "user": "👤"}

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar=icons[message["role"]]):
            st.markdown(message["content"])

    disable_chat = (
        "service_metadata" not in st.session_state
        or len(st.session_state.service_metadata) == 0
    )
    if question := st.chat_input("Ask a question...", disabled=disable_chat):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": question})
        # Display user message in chat message container
        with st.chat_message("user", avatar=icons["user"]):
            st.markdown(question.replace("$", "\$"))

        # Display assistant response in chat message container
        with st.chat_message("assistant", avatar=icons["assistant"]):
            message_placeholder = st.empty()
            question = question.replace("'", "")
            prompt, results = create_prompt(question)
            with st.spinner("Thinking..."):
                generated_response = complete(
                    st.session_state.model_name, prompt
                )
                # Build references table for citation
                markdown_table = "###### References \n\n| PDF Title | URL |\n|-------|-----|\n"
                for ref in results:
                    markdown_table += f"| {ref['relative_path']} | [Link]({ref['file_url']}) |\n"

                if results:
                    st.markdown(markdown_table)
                message_placeholder.markdown(generated_response.replace("$", "\$"))

            # Add assistant message to chat history
            st.session_state.messages.append({"role": "assistant", "content": generated_response})

if __name__ == "__main__":
    session = get_snowflake_session()
    root = Root(session)
    main()
