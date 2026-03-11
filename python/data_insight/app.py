import streamlit as st

## This is the main file for the data insight app. It imports the necessary modules and classes, and sets up the main class for the app.
from common.main_class import MainClass
from common.db import database_client   
from common.pg_dynamic_report import evaluate as dyreport

from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
import streamlit_mermaid as stmd

### initialize the memory and the main class
main_class = MainClass()
db_client = database_client()
memory = MemorySaver()
config = {"configurable": {"thread_id": "1"}}


### define global variables for the app
if "db_client" not in st.session_state:
    st.session_state.db_client = db_client.get_db_client()  
if "llm_client" not in st.session_state:
    st.session_state.llm_client = main_class.get_llm_client()

st.session_state.env="dev"



class State(TypedDict , total=False ):  # <--- add total=False This tells Python and Pydantic that not all fields are required, so you can pass partial state dictionaries without validation errors.
    def __init__(self):
        self.messages = []
    messages: Annotated[list, add_messages]
    is_chart: bool
    chart_data: object
    user_input: str
    thinking: bool
    is_erd: bool


## streamlite gui part


st.title("Echo Bot")

# Initialize chat history



if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    # print("Message in history: ", message)
    if message.get("chart", False):
        print("Rendering chart from history.")
        st.plotly_chart(message["content"])
    elif message.get("erDiagram", False):
        print("Rendering ERD from history.")
        stmd.st_mermaid(message["content"])
    else:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])




# React to user input
if prompt := st.chat_input("Say something"):
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user",'chart': False, "content": prompt})
    assistant_reply=dyreport(State , prompt)
    # print("X" * 80)
    # print("Assistant reply from dyreport is ", assistant_reply)
    # print("X" * 80)
    if isinstance(assistant_reply, dict) and assistant_reply.get("is_chart")  :  ##assistant_reply["is_chart"]:
        generated_key = main_class.generate_unique_key(num_random_strings=10)
        st.session_state.generated_key = generated_key  
        st.session_state.is_chart = True      
        # print("Received chart data in assistant reply.")
        # print(assistant_reply)
        chart_figure = assistant_reply.get("chart")
        if chart_figure is not None:
            print("Chart data is present in assistant reply.")
            st.plotly_chart(chart_figure )  # Render the chart using Streamlit's pyplot function
            st.session_state.messages.append({"role": "assistant",'chart': True , 'erDiagram': True, "content": assistant_reply["chart"]})            

        else:
            print("Chart data is missing in assistant reply.")
            st.session_state.messages.append({"role": "assistant",'chart': False, 'erDiagram': True, "content": 'No chart data'})

    elif isinstance(assistant_reply, dict) and assistant_reply.get("is_erd"):
        # print("Received ERD data in assistant reply.")
        # print(assistant_reply)
        erDiagram = assistant_reply.get("erDiagram")
        if erDiagram is not None:
            print("ERD data is present in assistant reply.")
            stmd.st_mermaid(erDiagram)  # Render the ERD using Streamlit's mermaid function
            st.session_state.messages.append({"role": "assistant", 'chart': False, 'erDiagram': True, "content": assistant_reply["erDiagram"]})
    else:
        # st.write("Received assistant reply:", assistant_reply[:100])  # print first 100 chars for brevity
        # Generate and display assistant response
        with st.chat_message("assistant"):
            response = f"Echo: {assistant_reply}"
            st.markdown(response)
        # Add assistant response to chat history
        st.session_state.is_chart = False
        st.session_state.is_erd = False
        st.session_state.messages.append({"role": "assistant",'chart': False, 'erDiagram': False, "content": response})



