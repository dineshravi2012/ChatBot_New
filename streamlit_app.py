import streamlit as st
import re
from snowflake.core import Root  # Requires snowflake>=0.8.0
from snowflake.cortex import Complete
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark import Session
from bs4 import BeautifulSoup

def load_svg(svg_filename):
    with open(svg_filename, "r") as file:
        return file.read()

# Load assistant and user icons from their respective SVG files
assistant_svg = load_svg("assets/chatbot.svg")
user_svg = load_svg("assets/user.svg")



# Define the greeting message
GREETING_MESSAGE = {"role": "assistant", "content": "Hello! Welcome to Informa AI. How can I assist you today?"}

# Import the fonts and inject custom CSS for assistant and user messages
st.markdown(
    """
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@600&display=swap" rel="stylesheet">
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
        background-color: #F7F7F7;  /* Set background color */
    }
    .stTextInput, .st-emotion-cache-1f3w014 {
        background-color: #F40000;  /* Input and button background */
        color: #FFFFFF;  
        border-radius: 70%;
       padding-left: 4px;            /* Text color */
    }
    .stMainBlockContainer {
       background-color: #F7F7F7;
       margin-top: -20%;
    }
    /* Assistant message container (aligned left) */
    .assistant-message-container {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        margin-bottom: 15px;
    }
    /* Assistant header: icon and name */
    .assistant-header {
        display: flex;
        align-items: center;
        margin-bottom: 5px;
    }
    .assistant-icon {
        margin-right: 5px;
        font-size: 24px;
    }
    .assistant-name {
        font-weight: 600;
        font-size: 14px;
        color: #333333;
    }
    /* Assistant message styling */
    .assistant-message {
        background: #FFFFFF 0% 0% no-repeat padding-box;
        box-shadow: -1px 1px 10px #E2E2E229;
        border: 0.5px solid #EAEAEA;
        border-radius: 0px 10px 10px 10px;
        opacity: 1;
        padding: 10px;
        text-align: left;
        font: normal normal 600 14px/20px 'Poppins', sans-serif;
        letter-spacing: 0px;
        color: #333333;
        max-width: 80%;
        word-wrap: break-word;
    }
    /* User message container (aligned right) */
    .user-message-container {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        margin-bottom: 15px;
    }
    /* User header: name and icon */
    .user-header {
        display: flex;
        align-items: center;
        margin-bottom: 5px;
    }
    .user-name {
        font-weight: 600;
        font-size: 14px;
        color: #black;
        margin-right: 5px;
    }
    .user-icon {
        font-size: 24px;
    }
    /* User message styling */
    .user-message {
        background: #FFF8F8 0% 0% no-repeat padding-box;
        box-shadow: -1px 1px 10px #E2E2E229;
        border: 0.5px solid #FF9090;
        border-radius: 10px 10px 0px 10px;
        opacity: 1;
        padding: 10px;
        text-align: left;
        font: normal normal medium 14px/20px 'Poppins', sans-serif;
        letter-spacing: 0px;
        color: #F40000;
        max-width: 80%;
        word-wrap: break-word;
    }
     /* Custom style for the chat input area */
    .stChatInput {
        background: #FFFFFF 0% 0% no-repeat padding-box;
        opacity: 1;
    }
    /* Custom style for the submit button */
    .stChatInputSubmitButton {
        background: #F40000 0% 0% no-repeat padding-box;
        opacity: 1;
    }
    </style>
    """,
    unsafe_allow_html=True
)

icons = {
    "assistant": assistant_svg,  # Loaded chatbot SVG
    "user": user_svg             # Loaded user SVG
}

# # Define icons using emojis for simplicity
# icons = {
#     "assistant": "🤖",  # Robot Face
#     "user": "🙋‍♀️"       # Person Raising Hand (Female)
# }

# Global variables to hold the Snowpark session and Root
snowpark_session = None
root = None

def get_snowflake_session():
    # Access credentials from Streamlit secrets
    snowflake_credentials = st.secrets["SF_Dinesh2012"]
    global snowpark_session, root
    if snowpark_session is None:
        try:
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
        except Exception as e:
            st.error(f"Failed to create Snowflake session: {e}")
            st.stop()
    return snowpark_session 

# Define available models (can be set to a default)
DEFAULT_MODEL = "mistral-large"
MODELS = [   
    "mistral-large",
    "snowflake-arctic",
    "llama3-70b",
    "llama3-8b",
]

def sanitize_chatbot_response(response):
    """
    Use BeautifulSoup to parse and clean the HTML response, ensuring
    that unmatched closing tags or extra tags are removed.
    """
    try:
        # Parse the response as HTML using BeautifulSoup
        soup = BeautifulSoup(response, "html.parser")
        
        # Extract text content if needed, removing any excessive HTML tags
        cleaned_response = soup.prettify()  # Optionally, can use soup.get_text() for plain text
        
        return cleaned_response
    except Exception as e:
        # If there's an error, return the raw response
        return response

# def sanitize_chatbot_response(response):
#     """
#     Remove unwanted HTML tags from the chatbot's response.
#     In this case, we are specifically removing closing </div> tags.
#     """
#     # Use regex to remove any unwanted </div> tags at the end of the response
#     cleaned_response = re.sub(r"</div>\s*$", "", response)
#     return cleaned_response

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
        try:
            services = snowpark_session.sql("SHOW CORTEX SEARCH SERVICES;").collect()
            service_metadata = []
            if services:
                for s in services:
                    svc_name = s["name"]
                    svc_search_col = snowpark_session.sql(f"DESC CORTEX SEARCH SERVICE {svc_name};").collect()[0]["search_column"]
                    service_metadata.append({"name": svc_name, "search_column": svc_search_col})
            st.session_state.service_metadata = service_metadata
        except Exception as e:
            st.error(f"Failed to fetch Cortex search services: {e}")
            st.session_state.service_metadata = []
    
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
   # answer = Complete(model, prompt, session=snowpark_session).replace("$", "\$")
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
                background-color: grey;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def main():
    # Initialize session state and other components
    init_session_state()
    init_service_metadata()
    init_messages()

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        if message["role"] == "assistant":
            # Assistant message container
            with st.container():
                st.markdown(f"""
                    <div class="assistant-message-container">
                        <div class="assistant-header">
                            <span class="assistant-icon">{icons.get("assistant", assistant_svg)}</span>
                            <span class="assistant-name">Informa AI</span>
                        </div>
                        <div class="assistant-message">{message["content"]}</div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            # User message container
            with st.container():
                st.markdown(f"""
                    <div class="user-message-container">
                        <div class="user-header">
                            <span class="user-name">You</span>
                            <span class="user-icon">{icons.get("user", user_svg)}</span>
                        </div>
                        <div class="user-message">{message["content"]}</div>
                    </div>
                    """, unsafe_allow_html=True)

    disable_chat = (
        "service_metadata" not in st.session_state
        or len(st.session_state.service_metadata) == 0
    )
    if question := st.chat_input("Type your message here...", disabled=disable_chat):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": question})
        # Display user message in chat message with styled rectangle
        with st.container():
            st.markdown(f"""
                <div class="user-message-container">
                    <div class="user-header">
                        <span class="user-name">You</span>
                        <span class="user-icon">{icons.get("user", user_svg)}</span>
                    </div>
                    <div class="user-message">{question}</div>
                </div>
                """, unsafe_allow_html=True)

        # Check if service metadata is available
        if "service_metadata" in st.session_state:
            try:
                 # Add a spinner while processing the response
             with st.spinner("Thinking..."):
                # Create a prompt for the language model
                prompt, results = create_prompt(question)
                # Get the response from the language model                
                answer = complete(st.session_state.model_name, prompt)
                # Sanitize the chatbot's response to remove any extra closing tags
                cleaned_answer = sanitize_chatbot_response(answer)
                # Add assistant's response to chat history
                st.session_state.messages.append({"role": "assistant", "content": cleaned_answer})

                # Display assistant's response in chat message with styled rectangle
                with st.container():
                    st.markdown(f"""
                        <div class="assistant-message-container">
                            <div class="assistant-header">
                                <span class="assistant-icon">{icons.get("assistant", assistant_svg)}</span>
                                <span class="assistant-name">Informa AI</span>
                            </div>
                            <div class="assistant-message">{cleaned_answer}</div>
                        </div>
                        """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"An error occurred while processing your request: {e}")

# Execute the app
if __name__ == "__main__":
    # Establish the Snowflake session
    get_snowflake_session()
    # Run the main function
    main()
