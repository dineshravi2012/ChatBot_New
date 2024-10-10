import streamlit as st
from snowflake.core import Root  # Requires snowflake>=0.8.0
from snowflake.cortex import Complete
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark import Session

# Define the greeting message
GREETING_MESSAGE = {"role": "assistant", "content": "Hello! 👋 I am your AI Chatbot. How can I assist you today?"}

# Import the font in the Streamlit app
st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Roboto&display=swap" rel="stylesheet">
    <style>
    body {
        font-family: 'Roboto', sans-serif;
    }
    .stChatMessage {
        font-family: 'Roboto', sans-serif;
    }
    /* Hide Streamlit default menu, footer, and header */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    /* Optional: Customize background color */
    .reportview-container {
        background-color: white;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Define icons using emojis for simplicity
icons = {
    "assistant": "🤖",  # Robot Face
    "user": "🙋‍♀️"       # Person Raising Hand (Female)
}

# Global variables to hold the Snowpark session and Root
snowpark_session = None
root = None

def get_snowflake_session():
    # Access credentials from Streamlit secrets
    snowflake_credentials = st.secrets["SF_Dinesh2012"]
    global snowpark_session, root
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
        root = Root(snowpark_session)  # Create the Root object
    return snowpark_session 

# Define available models (can be set to a default)
DEFAULT_MODEL = "mistral-large"
MODELS = [   
    "mistral-large",
    "snowflake-arctic",
    "llama3-70b",
    "llama3-8b",
]

def init_session_state():
    """Initialize session state variables.""" 
    if 'messages' not in st.session_state:
        st.session_state.messages = [GREETING_MESSAGE]
    if 'clear_conversation' not in st.session_state:
        st.session_state.clear_conversation = False
    if 'model_name' not in st.session_state:
        st.session_state.model_name = DEFAULT_MODEL  # Set default model
    if 'num_retrieved_chunks' not in st.session_state:
        st.session_state.num_retrieved_chunks = 5  # Default context chunks
    if 'num_chat_messages' not in st.session_state:
        st.session_state.num_chat_messages = 5  # Default chat history messages

def init_messages():
    """Initialize the session state for chat messages.""" 
    if st.session_state.clear_conversation:
        st.session_state.messages = [GREETING_MESSAGE]  # Reset to greeting message
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
    else:
        # Set default selected cortex search service
        if 'selected_cortex_search_service' not in st.session_state:
            st.session_state.selected_cortex_search_service = st.session_state.service_metadata[0]["name"]

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
        context_str += f"Context document {i+1}: {r[search_col]} \n\n"

    return context_str, results

def get_chat_history():
    """Retrieve the chat history from session state.""" 
    try:
        start_index = max(0, len(st.session_state.messages) - st.session_state.num_chat_messages)
        return st.session_state.messages[start_index:]
    except Exception as e:
        st.error("Error retrieving chat history. Please try again.")
        return []  # Return an empty list if an error occurs

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

    return summary

def create_prompt(user_question):
    """Create a prompt for the language model.""" 
    prompt_context, results = query_cortex_search_service(
        user_question,
        columns=["chunk", "file_url", "relative_path"],
        filter={"@and": [{"@eq": {"language": "English"}}]},
    )

    prompt = f"""
            [INST]
            You are a helpful AI chat assistant with RAG capabilities. When a user asks you a question,
            you will also be given context provided between <context> and </context> tags. Use that context
            to provide a summary that addresses the user's question. Ensure the answer is coherent, concise,
            and directly relevant to the user's question.

            If the user asks a generic question which cannot be answered with the given context,
            just say "I don't know the answer to that question."

            Don't say things like "according to the provided context."

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

hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            /* Optional: Customize background color */
            .reportview-container {
                background-color: white;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def main():
    # Initialize session state and other components
    init_session_state()
    init_service_metadata()
    init_messages()

    # Display controls above the chatbot
    with st.container():
        # Button to clear conversation
        if st.button("Clear Conversation"):
            st.session_state.messages = [GREETING_MESSAGE]  # Reset to greeting message
            st.success("Conversation cleared!")  # Optional: Display a success message

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"], avatar=icons.get(message["role"], "💬")):
            st.markdown(message["content"])

    disable_chat = (
        "service_metadata" not in st.session_state
        or len(st.session_state.service_metadata) == 0
    )
    if question := st.chat_input("Ask a question...", disabled=disable_chat):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": question})
        # Display user message in chat message
        with st.chat_message("user", avatar=icons.get("user", "🙋‍♀️")):
            st.markdown(question)

        # Check if service metadata is available
        if "service_metadata" in st.session_state:
            # Create a prompt for the language model
            prompt, results = create_prompt(question)
            # Get the response from the language model
            answer = complete(st.session_state.model_name, prompt)
            # Add assistant's response to chat history
            st.session_state.messages.append({"role": "assistant", "content": answer})

            # Display assistant's response in chat message
            with st.chat_message("assistant", avatar=icons.get("assistant", "🤖")):
                st.markdown(answer)

# Execute the app
if __name__ == "__main__":
    # Establish the Snowflake session
    get_snowflake_session()
    # Run the main function
    main()
