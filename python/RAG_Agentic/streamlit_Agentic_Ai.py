from pprint import pprint
import os
import sys
import json
import yaml
from  typing import Optional
## import modules
from gradio import Image
import streamlit as st
from streamlit_carousel import carousel
from langchain_core.runnables import RunnableLambda
## langchain
# from typing import Annotated

from typing_extensions import Annotated
from typing_extensions import TypedDict
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from typing_extensions import Annotated
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition
import plotly.express as px
import urllib.parse
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain.agents.agent_types import AgentType
from pathlib import Path
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine
import urllib
from PIL import Image
import io
import re
import pandas as pd
import numpy as np

from langchain_community.utilities import OpenWeatherMapAPIWrapper
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool
# from langchain_community.tools  import QuerySQLDataBaseTool 
from langgraph.checkpoint.memory import MemorySaver

## import logging to create log out on console for testing
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory = MemorySaver()
config = {"configurable": {"thread_id": "1"}}

# Add the directory containing your_module_name.py to sys.path
# Replace '/path/to/your/directory' with the actual path
# sys.path.append(os.path.abspath('C:\genai\Code\stremlit')) 
# import main_class
# model = main_class.model()

import sys
sys.path.append(r"C:\genai\Code\stremlit")  # Adjust the path as needed
from mainclass import MainClass
main_class = MainClass() 

llm = main_class.model()




database = "demo"
# database="AdventureWorks"
table = "dbo.orders"
# table = "SalesLT.Product"
username = "demo_user"
password = "demo123"
server = r"LAPTOP-QSH9GD6T\SQLEXPRESS"

conn_str = f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+11+for+SQL+Server"

db = SQLDatabase.from_uri(conn_str)

# Tool to query SQL Server
query_sql_tool = QuerySQLDataBaseTool(db=db)
                 
# --------------- 🌦️ Weather Tool ---------------
# weather_tool = OpenWeatherMapQueryRun(openweathermap_api_key ="f422746dad79b71d0156b746d847888b")
weather = OpenWeatherMapAPIWrapper(openweathermap_api_key ="f422746dad79b71d0156b746d847888b")





### ***********************  code   ***********************


class State(TypedDict , total=False ):  # <--- add total=False This tells Python and Pydantic that not all fields are required, so you can pass partial state dictionaries without validation errors.
    def __init__(self):
        self.messages = []
    messages: Annotated[list, add_messages]
    question: str
    query: str
    result: str
    answer: str  
    output : str
    chart_type : str
    from_query : bool
    uploaded_file : str



def ensure_ai_message(state):
    messages = state.get("messages", [])
    if not any(isinstance(m, AIMessage) for m in messages):
        messages = [AIMessage(content="")] + messages
    state["messages"] = messages
    return state



def get_weather(state: State):
    """ get the city name from prompt or message """
    logger.info(" debug :  get the city name from prompt or message ")
    
    user_input = state["messages"][-1].content
    logger.info(f"***get_weather   user input **{user_input}* ")
    
    res = llm.invoke([
        HumanMessage(content=f"""
        You are given a question and must extract the city name from it.
        Respond ONLY with the city name. If no city is found, respond with an empty string.
        Question: {user_input}
        """)
        ])
    city_name = res.content.strip()
    # if not city_name:
        # return {"messages": [AIMessage(content="I couldn't find a city name in your question.")]}
    # return {"messages": [AIMessage(content=f"Extracted city: {city_name}")], "city": city_name}
    # """Get current weather for a given city."""
    logger.info(f"🚨 ROUTER DEBUG: state = {city_name}")
    return weather.run(city_name)





def get_db_connection(server, database, username, password):
    """
    Connect to the SQL Server database using the provided credentials.
    """
    conn_str = f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+11+for+SQL+Server"

    # Create a SQLAlchemy engine
    db2_conn = SQLDatabase.from_uri(conn_str)
    return db2_conn

system_message = """
Given an input question, create a syntactically correct {dialect} query to
run to help find the answer. Unless the user specifies in his question a
specific number of examples they wish to obtain, always limit your query to
at most {top_k} results. You can order the results by a relevant column to
return the most interesting examples in the database.

Never query for all the columns from a specific table, only ask for a the
few relevant columns given the question.

Pay attention to use only the column names that you can see in the schema
description. Be careful to not query for columns that do not exist. Also,
pay attention to which column is in which table. according to sql server {dialect} query syntax.

Only use the following tables:
{table_info}
"""

user_prompt = "Question: {input}"


query_prompt_template = ChatPromptTemplate(
    [("system", system_message), ("user", user_prompt)]
)

class QueryOutput(TypedDict):
    """Generated SQL query."""

    query: Annotated[str, ..., "Syntactically valid SQL query."]

# classification_prompt = ChatPromptTemplate.from_messages([
#     ("system", "Classify the user intent into one of: ['weather', 'database', 'other']."),
#     ("human", "User message: {input}")
# ])



def write_query(state: State) -> dict:
    """Generate SQL query to fetch information."""
    logger.info(f" 🚨 DEBUG write_query {state.get('question')}" )
    try:
        db = get_db_connection(server, database, username, password)
        question = state.get("question")
        if not question:
            messages = state.get("messages", [])
            if messages and isinstance(messages[-1], HumanMessage):
                question = messages[-1].content
            # else:
            #     question = ""
                    
        prompt = query_prompt_template.invoke(
            {
                "dialect": db.dialect,
                "top_k": 10,
                "table_info": db.get_table_info(),
                "input": question,   ##state["question"]
            }
        )
        structured_llm = llm.with_structured_output(QueryOutput)
        result = structured_llm.invoke(prompt)
        logger.info("Generated Query:", result["query"])
        return {"query": result["query"]}
    except Exception as e:
        logger.info("write_query failed:", e)
        return {"query": ""}



def execute_query(state: State):
    """Execute SQL query."""
    logger.info(" 🚨 DEBUG execute_query ")
    db = get_db_connection(server, database, username, password)
    execute_query_tool = QuerySQLDatabaseTool(db=db)
    return {"result": execute_query_tool.invoke(state["query"])}




def generate_answer(state: State):
    """Answer question using retrieved information as context."""
    try:
        logger.info("🚨 DEBUG: generate_answer called")
        question = state.get("question", "")
        query = state.get("query", "")
        result = state.get("result", "")
        

        if not (question and query and result):
            raise ValueError("Missing input for generate_answer")

        prompt = (
            "Given the following user question, corresponding SQL query, "
            "and SQL result, answer the user question.\n\n"
            f'Question: {question}\n'
            f'SQL Query: {query}\n'
            f'SQL Result: {result} as a table format'
        )

        response = llm.invoke(prompt)
        # logger.info(" response from generated_answer" , response)

        
        print("✅ Answer Generated response :", response.content)
        # print("✅ Answer Generated response.content[0]:", response.content[:])
        return {"messages": response.content}
    except Exception as e:
        print("❌ ERROR in generate_answer:", e)
        return {"answer": "An error occurred while generating the answer."}




# ----------------------------
# 2. State Setup
# ----------------------------

# class State(dict):
#     pass

classification_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that classifies user input into one of these categories: 'weather', 'database', 'chart' 'file' or 'other'. Respond ONLY with one of these words. Do not explain."),
    ("human", "User: What's the weather in Delhi?"),
    ("ai", "weather"),
    ("human", "User: sum all the customer country and their opening amount  from table customer without any row limit and create a line chart"),
    ("ai", "chart"),   
    ("human", "User: create a chart or grapgh"),
    ("ai", "chart"),          
    ("human", "User: Count the number of customers from table Customer"),
    ("ai", "database"),
    ("human", "User: analysis the data from the file"),
    ("ai", "file"),    
    ("human", "User: analysis the data and recommend your suggestion for the file"),
    ("ai", "file"),        
    ("human", "User: show chart using column country and sale price for all country from uploaded file"),
    ("ai", "file"),   
    ("human", "User: list column country and sale price for all country from uploaded file and sum of by country. create bar chart"),
    ("ai", "file"),          
    ("human", "User: Tell me a joke"),
    ("ai", "other"),
    ("human", "User: {input}")
])


def detect_intent(user_input: str) -> str:
    try:
        prompt = classification_prompt.invoke({"input": user_input})
        result = llm.invoke(prompt)
        logger.info("result ** {result}")
        # return result.content.strip().lower()
        intent = result.content.strip().lower()
        logger.info(f" ********* detect_intent  intent value is **{intent}**   ")
        if intent not in ["weather", "database", "chart" ,"file"]:
            return "other"
        return intent
    except Exception as e:
        logger.info("❌ Intent detection failed:", e)
        return "other"

def route(state: State) -> dict:
    
    print("** DEBUG  route(state: State) : ** ", state)


    messages = state.get("messages", [])

    if not any(isinstance(m, AIMessage) for m in messages):
        messages = [AIMessage(content="")] + messages
        
    if messages and isinstance(messages[-1], HumanMessage):
        user_input = messages[-1].content.strip().lower()
    else:
        user_input = "default"

    intent = detect_intent(user_input).strip().lower()        
    print(f"[Router] input = {user_input}")
    print("*" * 50)
    print(f"  ***   outside the if condition func route   intent value is   *{intent}*")
    print("*" * 50)
    if  "weather" in intent:
        print(f"🌦️ Route: weather_node  message **{messages} **")
        return {"next": "weather_node", "messages": user_input}
    elif "database" in intent:    ###any(k in user_input for k in ["table", "database", "query", "sql", "data", "record", "column"]):     ###intent == "database":
        print(f"📊 **********************   Route: table_node 222222 [{intent}]  *************************************")
        return {"next": "table_node", "messages": messages, "question": user_input}
    elif "chart" in intent:
        print("📊  **********************  Route: chart_node    **********************")
        return {"next": "chart_node", "messages": user_input}
    elif "file" in intent:
        print("📊  **********************  Route: file Node    **********************")
        return {"next": "file_node", "messages": messages, "question": user_input}
        # return {"next": "file_node", "messages": user_input}    
    else:
        print("❓ Route: default")
        return {"next": "default", "messages": messages}    
# ---------------  Old code  -------------------    
## 31 july version
# def route(state: State) -> dict:
    
#     logger.info("** DEBUG  route(state: State) : ** ", state)


#     messages = state.get("messages", [])

#     if not any(isinstance(m, AIMessage) for m in messages):
#         messages = [AIMessage(content="")] + messages
        
#     if messages and isinstance(messages[-1], HumanMessage):
#         user_input = messages[-1].content.strip().lower()
#     else:
#         user_input = "default"

#     intent = detect_intent(user_input).strip().lower()        
#     logger.info(f"[Router] input = {user_input}")

#     logger.info(f"  ***   outside the if condition func route   intent value is   *{intent}*")

    
#     if  "weather" in intent:
#         logger.info(f"🌦️ Route: weather_node  message **{user_input} **")
#         return {"next": "weather_node", "messages": user_input}
#     elif any(k in user_input for k in ["table", "database", "query", "sql", "data", "record", "column"]):     ###intent == "database":
#         logger.info(f"📊 Route: table_node user_input  ** {user_input} ** ")
#         logger.info(f"📊 Route: table_node  messages ** {messages} **  ")
#         return {"next": "table_node", "messages": messages, "question": user_input}
#     elif "chart" in intent:
#         logger.info("📊 Route: chart_node")
#         return {"next": "chart_node", "messages": user_input}    
#     else:
#         logger.info("❓ Route: default")
#         return {"next": "default", "messages": messages}    
    
# def table_tool_node(state: dict):
#     # Extract the latest user message as the question
#     messages = state.get("messages", [])
#     if messages and isinstance(messages[-1], HumanMessage):
#         question = messages[-1].content
#     else:
#         question = ""

#     # Create the tool chain state
#     tool_state = State(
#         messages=messages,
#         question=question,
#         query="",
#         result="",
#         answer=""
#     )

#     # Create a chain of tools
#     chain = ToolNode(tools)
#     result = chain.invoke(tool_state)
    
#     # Return result as messages
#     return {"messages": [AIMessage(content=str(result))]}


def table_tool_node(state: State) -> State:
    logger.info("🚨 Entered table_tool_node")

    # Step 1: Write SQL query
    result1 = write_query(state)
    state.update(result1)
    logger.info("✅ write_query output:", result1)

    # Step 2: Execute SQL query
    result2 = execute_query(state)
    state.update(result2)
    logger.info("✅ execute_query output:", result2)

    # Add to messages for UI
    
    # chart_type = get_chart_type(state.get('question'))
    # if chart_type:  
    #     # state["messages"].append(AIMessage(content=f"Chart type detected: {chart_type}"))
    #     state["chart_type"] = chart_type
    #     logger.info(f"🚨 chart_type detected: {chart_type}")  
    state["from_query"] = True
    #     create_chart(state) 
    # else:
    # Step 3: Generate final answer
    result3 = generate_answer(state)
    state.update(result3)
    logger.info("✅ generate_answer output:", result3)        
    
    # state["messages"] = state.get("messages", []) + [AIMessage(content=state.get("answer", "No answer"))]
    state["messages"] = state.get("messages")
    return state





def get_chart_type(state: State):
    """ get the chart type from prompt or message """
    question = state.get("question")
    
    if not question:
        messages = state.get("messages", [])
        if messages and isinstance(messages[-1], HumanMessage):
            question = messages[-1].content
        # else:
        #     question = ""
    
    # To get the content string:
    # user_message = state.get("question")  # Get the last message object
    # content = user_message.content        # Extract the content attribute

    # state["messages"] = messages
    print(f'🚨 Entered get_chart_type ************************[{question}]************************************')
    print(f" debug :  get the chart type from prompt or message  ")
    # question = state.get("question", "")
    query = state.get("query", "")
    result = state.get("result", "")
    print(f"***get_chart_type   question **{question}* ")
    print(f"***get_chart_type   query **{query}* ")     
    print(f"***get_chart_type   result **{result}* ")
  
  
    user_input = state["messages"][-1].content

    res = llm.invoke([
        HumanMessage(content=f"""
        1. You are a helpful assistant that extracts the chart type from user input.
        2. You will be given a question and must extract the visualization type from it.                         
        3. Respond ONLY with the visualization type. If no visualization is found, respond with an empty string.
        4. The visualization types can be: 'bar', 'line', 'scatter', 'pie', 'histogram', 'boxplot', 'heatmap', 'area', 'donut', 'radar', 'funnel', 'treemap', or 'wordcloud'.
        5. If the question does not specify a visualization type, respond with an empty string  
        Question: {question}
        """)
        ])
    chart_name = res.content.strip()
    if not chart_name:
        print("🚨 No chart type found in the question.")
        return None
    state["chart_type"] = chart_name
    # return {"chart_type" :chart_name }
    state["chart_type"]= chart_name
    return state

# def create_chart(state :State , df:Optional[pd.DataFrame] = None) -> State:
def create_chart(state :State ) -> State:
    """Create a chart or graph using the dataframe result set"""
    print("🚨 Entered create_chart ************************************************************")
    # user_input = state["messages"][-1].content
    # chart_type = get_chart_type(state.get('question'))
    
    # chart_type = get_chart_type(state)
    get_chart_type(state)
    if not state.get("chart_type"):
        print("🚨 No chart type found in the state.")
        return {"messages": [AIMessage(content="No chart type specified.")]}
    # state["messages"] = state.get("messages", []) + [AIMessage(content=f"Chart type determined: {state['chart_type']}")]    

    chart_funcs = {
        "bar": px.bar,
        "line": px.line,
        "scatter": px.scatter,
        "pie": px.pie,
        "box": px.box,
        "area": px.area,
        "histogram": px.histogram,
        "heatmap": px.imshow,  # Note: px.imshow is typically used for heatmaps
        "donut": px.pie,  # Donut charts can be created using pie charts with hole parameter
        "radar": px.line_polar,  # Radar charts can be created using line_polar
        "funnel": px.funnel,  # Funnel charts can be created using funnel
        "treemap": px.treemap,
        "wordcloud": px.imshow ,  # Word clouds can be created using imshow with a generated image
    }
    
    # if df is None:
    print("🚨 No DataFrame provided. Fetching data from query.")
        # If no DataFrame is provided, fetch data using the query
        # if not state.get("from_query", False):
        #     print("🚨 create_chart: from_query is False. Cannot create chart without a DataFrame.")

        # else:
    message = write_query(state)
    question = state.get("question", "")
    # query = state.get("query", "")
    # result = state.get("result", "")
    # print(f" result *** {result}")
    # if state["from_query"] :
    print("🚨 create_chart called with from_query set to True. Proceeding with chart creation.")
    df = pd.read_sql(message['query'],  db._engine.connect()  )
    # else:
    #     df = df

    df_columns =df.columns
    column_names_list = df.columns.tolist()
    # fig = px.bar
    print("@"  * 80)
    print(f" message  {message} " ) 
    ## output from above line 
    ##  message  {'query': 'SELECT CUST_COUNTRY, SUM(OPENING_AMT) AS TotalOpeningAmount FROM CUSTOMER GROUP BY CUST_COUNTRY'}
    print("@"  * 80)  
    # Add a super title to the figure, which is centered by default
      
    if 'pie' in state["chart_type"] or 'donut' in state["chart_type"]:
        fig = chart_funcs[state["chart_type"]](df, names=column_names_list[0], values=column_names_list[1], hole=0.3 if 'donut' in state["chart_type"] else 0)  
    elif 'radar' in state["chart_type"]:
        fig = chart_funcs[state["chart_type"]](df, r=column_names_list[1], theta=column_names_list[0])  
    else:
        fig = chart_funcs[state["chart_type"]](df,
                    x=column_names_list[0],
                    y=column_names_list[1] 
                    #  size="TotalOpeningAmount", # Make marker size proportional to population
                    #  color="CUST_COUNTRY",      # Color markers by city
                    #  hover_name="CUST_COUNTRY", # Show city name on hover
                    , title=f"{column_names_list[0]}  vs. {column_names_list[1]}"
                    )
            
    print("🚨 create_chart: Chart created successfully.")
    print(({"role": "assistant", "content": "Here's your chart!", "chart": fig}))
    
    return ({"role": "assistant", "content": "Here's your chart!", "chart": fig})
    # return ({"role": "assistant", "content": "How can I help you?"})  ##{"messages": "chart created successfully."}    ##{"query" :state["chart_type"] }

def is_chart_request(user_input: str) -> bool:
    return bool(re.search(r"\b(chart|graph|plot|visualize)\b", user_input.lower()))


def contains_chart_intent(user_input: str) -> bool:
    chart_keywords = ["chart", "graph", "bar chart", "line chart", "pie chart", "visualize", "plot"]
    return any(keyword in str(user_input).lower() for keyword in chart_keywords)


###   analsis the upload csv., excel files
def file_analysis(state : State) -> State:
    """Analyze the uploaded file and return a summary."""
   
    # Read the file into a DataFrame
    # try:
    state["chart_type"] = None
    get_chart_type(state)
    pandas_df = main_class.get_data_frame_from_file()
    pandas_df = pandas_df.convert_dtypes()    

    # print("P" * 100 )
    # print(f' state["chart_type"]    **{state["chart_type"]==None}**')
    # print("P" * 100 )

    if  len(state["chart_type"].strip()) <= 2:   ##state["chart_type"] is None and
        # System message
        print("🚨 Entered file_analysis ************************************************************")
        

        if pandas_df is None:
            print("🚨 Error: No DataFrame found. Please upload a valid file.")
            return {"messages": [AIMessage(content="Error: No DataFrame found. Please upload a valid file.")]}  
        else:
            print("🚨 Successfully loaded DataFrame:")
            # print(pandas_df.head(2))
            # print(f"🚨 Successfully loaded DataFrame: {pandas_df.head(5)}")

        # Generate a summary of the DataFrame
        agent = create_pandas_dataframe_agent(
            llm=llm,
            df=pandas_df,
            verbose=False,
            prefix ="You are a data analyst AI. You are going to help user to analyze the data and output as tabular format",
            # suffix = "show data into a tabular format from the dataframe",
            # agent_type="tool-calling"  , ##AgentType.OPENAI_FUNCTIONS , # recommended for GPT-4-turbo or GPT-3.5-turbo
            # agent_type=AgentType.OPENAI_FUNCTIONS , # recommended for GPT-4-turbo or GPT-3.5-turbo
            allow_dangerous_code=True , # ⬅️ this enables Python REPL
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            include_df_in_prompt = True ,
            number_of_head_rows = 10,  # Number of rows to show in the DataFrame preview
            agent_executor_kwargs={"handle_parsing_errors": True} ,
            # handle_parsing_errors=True    ,  
            # agent_kwargs={
            #     "system_message": (
            #     "You are a data analysis expert. Use the DataFrame provided to answer all user questions using charts, summaries, and stats."
            #                     )}
        )

        # pandas_df.head(10)
        # print("d" * 50)
        # print(f"state['messages'][-1].content    {state['messages'][-1].content}")
        # print("d" * 50)
        user_input = {state['messages'][-1].content} 
        state["question"] = state['messages'][-1].content

        # print(f"state['question']   {state['question']}")
        # print(f"state['question'] type **  {type(state['question'])} **")

        response = agent.run({state['messages'][-1].content} )
        # response = agent.run("Show me the summary of the dataframe in tabular format")
        print("s" * 50)
        print(f"response: {response}")
        print("s" * 50)

        state["messages"] = response
        # st.session_state.history["user_input"] = user_input
        # st.session_state.history["question"] = state["question"]
        # st.session_state.history["messages"] = response
        # st.session_state.history["content"] = response

        print("V" * 50)
        print(f" user input string   *** {user_input}  and chart type ** [{len(state['chart_type'].strip())}]  **")
        print("V" * 50)


            # return(create_chart(state  , df= pandas_df))
            # print("x" * 50)
            # return ({"role": "assistant", "content": response, "chart": st.session_state.figure})
        
        print("y" * 50)
        print("no chart data ")
        print("y" * 50)
        return ({"role": "assistant", "messages": response}) # return response without chart
    else:
        
        # If the response contains a chart request, create the chart
        # print("x" * 50)
        # print("🚨 file_analysis: Chart request detected in response. Creating chart.")
        # state["dataframe"] = pandas_df  # Store the DataFrame in state for chart creation

        return(create_chart_4_file(state , pandas_df)  )

            # return state
                
            # return ({"role": "assistant", "content": response , "chart": st.session_state.figure})
            # print("\n📊 Result:", response)
        # except Exception as e:
        #     return {"messages": [AIMessage(content=f"Error analyzing file: {str(e)}")]}

### prompt to test 
# list column country and sale price for all country from uploaded file and group by country
# list column country and sale price for all country from uploaded file and sum of by country
###

def create_chart_4_file(state :State , pandas_df: pd.DataFrame) -> State:
    """Analyze the uploaded file and return a summary as dataframe"""
    # """return a summerized dataframe from pandas dataframe result set"""
    print("🚨 Entered create_chart ************************************************************")
   
##   show chart using column country and sale price for all country from uploaded file

    # try:
    chart_funcs = {
        "bar": px.bar,
        "line": px.line,
        "scatter": px.scatter,
        "pie": px.pie,
        "box": px.box,
        "area": px.area,
        "histogram": px.histogram,
        "heatmap": px.imshow,  # Note: px.imshow is typically used for heatmaps
        "donut": px.pie,  # Donut charts can be created using pie charts with hole parameter
        "radar": px.line_polar,  # Radar charts can be created using line_polar
        "funnel": px.funnel,  # Funnel charts can be created using funnel
        "treemap": px.treemap,
        "wordcloud": px.imshow ,  # Word clouds can be created using imshow with a generated image
    }
    print(f'Create a chart or graph using the dataframe result set **{state }**')

        
    # if state["from_query"] :
    print(f"🚨 create_chart called with from_query set to True. Proceeding with chart creation. {state['question']}")
    # df_0 = state["dataframe"]    ###state.get("dataframe", pandas_df)  # Assuming pandas_df is the DataFrame you want to use
    # print(df)

    system_msg = ("You are a data developer expert AI. "
                "fetch the asked data from the source and convert into a dataframe, so it used in visualization")
    
    # Generate a summary of the DataFrame
    agent = create_pandas_dataframe_agent(
        llm=llm,
        df=pandas_df,
        verbose=True,
        prefix =f"You are a data analyst AI. You are going to help user to get the summarized dataframe for {format(state['question'])} and return a dataframe",
        # suffix = "show data into a tabular format from the dataframe",
        # agent_type="tool-calling"  , ##AgentType.OPENAI_FUNCTIONS , # recommended for GPT-4-turbo or GPT-3.5-turbo
        # agent_type=AgentType.OPENAI_FUNCTIONS , # recommended for GPT-4-turbo or GPT-3.5-turbo
        allow_dangerous_code=True , # ⬅️ this enables Python REPL
        agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        include_df_in_prompt = True ,
        number_of_head_rows = 10,  # Number of rows to show in the DataFrame preview
        agent_executor_kwargs={"handle_parsing_errors": True} ,
    )        
    # agent = create_pandas_dataframe_agent(
    #     llm=llm,
    #     df=pandas_df,
    #     verbose=True,
    #     prefix ="You are a data developer expert AI. ",
    #     suffix = f"only return dataframe for only the asked columns names as mention in dataframe from {state['question']}",
    #     # suffix ="Use df[['country', 'sale_price']] to display only those columns in case sensitive format." ,
    #     # agent_type="tool-calling"  , ##AgentType.OPENAI_FUNCTIONS , # recommended for GPT-4-turbo or GPT-3.5-turbo
    #     agent_type=AgentType.OPENAI_FUNCTIONS , # recommended for GPT-4-turbo or GPT-3.5-turbo
    #     # handle_parsing_errors=True,
    #     allow_dangerous_code=True ,  # ⬅️ this enables Python REPL
    #     # system_message=system_msg
    # )

    


    
    # response = agent.run({state["question"] } )
    response = agent.run({state['messages'][-1].content})  # Convert the response to a DataFrame if needed
    df = main_class.convert_string_to_data_frame(response)
    # df = main_class.extract_table_from_text(response)
    
    print("B" * 50)
    print(f" response from create_chatrt_4_file   {response}")
    print(f" dataframe type  ***> {type(df)} <*** ")
    print("B" * 50)
    

    print("C" * 50)
    print(f"🚨 create_chart_4_file called with chart_type: {state['chart_type']}    ")  
    print("C" * 50)
    # if df is None or df.empty:
    #     print("E" * 50)
    #     print("🚨 create_chart: DataFrame is empty or not provided.")
    #     print("E" * 50) 
    #     return {"messages": [AIMessage(content="No data available to create a chart.")]}
        
    df_columns =df.columns
    column_names_list = df.columns.tolist()
    # fig = px.bar
    print("A" * 80)
    print(f" chart type is ** {state['chart_type']}   **")
    print(f" data frame columns are ** {df.columns.tolist()} **"    )
    # get_chart_type(state)
    print("A" * 80)
    # state["chart_type"] ="bar"
    if 'pie' in state["chart_type"] or 'donut' in state["chart_type"]:
        fig = chart_funcs[state["chart_type"]](df, names=column_names_list[0], values=column_names_list[1], hole=0.3 if 'donut' in state["chart_type"] else 0)  
    elif 'radar' in state["chart_type"]:
        fig = chart_funcs[state["chart_type"]](df, r=column_names_list[1], theta=column_names_list[0])  
    else:
        print("z" * 80)
        fig = chart_funcs[state["chart_type"]](df,
                    x=column_names_list[0],
                    y=column_names_list[1]
                    )
    
    print("🚨 create_chart: Chart created successfully.")
    print(({"role": "assistant", "content": "Here's your chart!", "chart": fig}))
    
    # return ({"role": "assistant", "content": "Here's your chart!", "additional_kwargs":{"chart": fig}})

    return {
        "messages": [
            AIMessage(
                content="Here's your chart!",
                additional_kwargs={"chart": fig}
            )
        ]
    }    


        # return state
    # except Exception as e:
    #     logging.error(f"❌ Error in create_chart_4_file: {str(e)}")
    #     return {"messages": [AIMessage(content=f"Error creating chart: {str(e)}")]} 
        

    

    





weather_tool = RunnableLambda(lambda state: {"messages": get_weather(state)})
chart_tool = RunnableLambda(lambda state: {"messages": create_chart(state)})




# ------------------------
# 4. Create LangGraph
# ------------------------

def default_response(state: State) -> State:
    # return {"messages": [model.invoke(state["messages"])]}
    return {"messages": [llm.invoke(state["messages"])]}
# ----------------------------
# 4. LangGraph Creation
# ----------------------------

graph = StateGraph(State)
graph.add_node("router", route)
graph.add_node("weather_tool", weather_tool)
graph.add_node("create_chart", chart_tool)

graph.add_node("table_tool", table_tool_node)

graph.add_node("default", default_response)
graph.add_node("file_analysis", file_analysis)
graph.set_entry_point("router")
# graph.add_conditional_edges(
#     "router", lambda state: route(state),
#     {
#         "weather_tool": "weather_tool",
#         "table_tool": "table_tool",
#         "default": "default"
#     }
# )
graph.add_conditional_edges(
    "router",
    # 👇 key to look inside router's return value
    lambda state: state["next"],
    path_map={
        "weather_node": "weather_tool",
        "table_node": "table_tool",
        "chart_node" : "create_chart" ,
        "file_node" : "file_analysis" ,
        "default": "default"
    }
)
graph.add_edge("weather_tool", END)
# graph.add_edge("table_tool", "create_chart")
graph.add_edge("default", END)

app = graph.compile()

# chat_graph = graph.compile()


# state["messages"]=Image(graph.get_graph().draw_mermaid_png())



## *******************************************************  start sidebar configuration  *******************************************************
# Set up sidebar title

sidebarcontainer = st.sidebar.title("Configuration")

# read cong=fig.yaml files and populate sidebar
with open("C:\genai\Code\stremlit\config.yaml", 'r') as file :
    config_data = yaml.safe_load(file)    

pandas_df=pd.DataFrame()
pandas_df = main_class.populate_sidebar(st=st, config_data=config_data)
if pandas_df is not None:
    st.session_state["dataframe"] = pandas_df
    print("🚨 DEBUG: DataFrame loaded into session state.")
    pandas_df.head(10)  # Display the first 10 rows of the DataFrame in the sidebar

## *******************************************************  End sidebar configuration  *******************************************************

# ------------------------
# 5. Streamlit UI
# ------------------------
# st.title("🧠 LangGraph Chatbot")

if "history" not in st.session_state:
    st.session_state["history"] = []

# Input from user
user_input = st.chat_input("Say something...")

# Render message history
for msg in st.session_state.history:
    print(f"🚨 DEBUG: session_state = {msg}")
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
       
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(msg.content)
    ai_response_message = msg
    if 'chart' in ai_response_message.additional_kwargs:
        chart_figure = ai_response_message.additional_kwargs['chart']
        # st.pyplot(chart_figure)
        st.plotly_chart(chart_figure, key = st.session_state.generated_key)            
    # if isinstance(msg, dict) and msg.get("type") == "chart":
    #     print("4" * 50  )
    #     st.plotly_chart(msg["figure"], use_container_width=True)


# Process new input
if user_input:
    user_msg = HumanMessage(content=user_input)
    with st.chat_message("user"):
        st.markdown(user_msg.content)    
    st.session_state.history.append(user_msg)
    logger.info(" ****************************************************************************************")
    # result = app.invoke({"messages": [HumanMessage(content=st.session_state.history)] }, config=config)
    result = app.invoke({"messages": st.session_state.history}, config=config)

    print("H" * 100)
    print(result["messages"])
    print("H" * 100)
    st.session_state.history = result["messages"]

    # Display the assistant's message
    with st.chat_message("assistant"):
        st.markdown(st.session_state.history[-1].content)

        ai_response_message  = st.session_state.history[-1]
        
        if 'chart' in ai_response_message.additional_kwargs:
            generated_key = main_class.generate_unique_key(num_random_strings=10)
            st.session_state.generated_key = generated_key
            chart_figure = ai_response_message.additional_kwargs['chart']
            # st.pyplot(chart_figure)
            st.plotly_chart(chart_figure , key =generated_key)
        elif 'chart' in ai_response_message:
            generated_key = main_class.generate_unique_key(num_random_strings=10)
            st.session_state.generated_key = generated_key
            chart_figure = ai_response_message['chart']
            # st.pyplot(chart_figure)
            st.plotly_chart(chart_figure , key =generated_key)       
        else:
            print("N" * 100)
            print(ai_response_message)
            print("No 'chart' key found in additional_kwargs.")    
            print("N" * 100)    
        # if "chart" in (vars(st.session_state.history[-1])):    ## st.session_state.history[-1])["additional_kwargs"]:
        #     st.pyplot((st.session_state.history[-1])["additional_kwargs"]["chart"]) # Or st.plotly_chart(msg["chart"])   
    # print("6" * 50  )
    # print(" file name " , file_upload )
    # print("6" * 50  )
