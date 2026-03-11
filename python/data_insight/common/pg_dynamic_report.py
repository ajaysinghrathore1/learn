from typing import Literal
from pydantic import BaseModel
import asyncio
import sys
import os
import re
import pandas as pd
import json
import seaborn as sns
import matplotlib.pyplot as plt
import io
import base64
import streamlit as st
from sympy import false
import plotly.express as px
# import sys
# print("PY EXE:", sys.executable)
# print("SYS PATH[0]:", sys.path[0])

from langchain_core.messages import SystemMessage, HumanMessage , AIMessage,ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from langgraph.checkpoint.memory import MemorySaver
# from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent, SQLDatabaseToolkit
from langchain.agents import create_agent  
from langgraph.checkpoint.memory import InMemorySaver

memory = MemorySaver()
config_memory = {"configurable": {"thread_id": "1"}}


import warnings
warnings.filterwarnings("ignore", message="Empty session id, using global scope instead")

import warnings
warnings.filterwarnings('ignore')


# from fastmcp import Client , Context
from common.main_class import AZURE_OPENAI_DEPLOYMENT, MainClass
from common.schema_detail import schema_details
import traceback
# ---------- Azure OpenAI client ----------



# ### declare variables
# # Each message: (message_id, content, sender_id)
# users: List[str] = ["you", "assistant"]
# messages: List[Tuple[str, str, str]] = [   ##a message identifier, a message content, and a user identifier.
#     (
#         "welcome",
#         "👋 **Hi, I’m your Azure OpenAI assistant for dynamic report and metadata analysis**",
#         "assistant",
#     )
# ]

messages_payload = []
user_input=""
current_prompt=""
thinking = False
schema_detail = None
llm_client = MainClass().get_llm_client()
schema_name="public"
is_chart=False
image_data=None
is_erd=False
chart_type=None
# # Make sure these exist once (init)
# messages = []
# msg_seq = 0

host = "localhost"
database = "postgres"
user = "postgres"
password = "postgres"
port = "5432"    
schem_cls = schema_details( host, database, user, password, port )
db_ = schem_cls.get_db_conn()

toolkit = SQLDatabaseToolkit(db=db_, llm=llm_client, config=config_memory)

class IntentOut(BaseModel):
    intent: Literal["weather", "chart" ,  "chart", "database" ,  "other", 'ERD'] ##"schema", "code","file" ,  "chart"

intent_llm = llm_client.with_structured_output(IntentOut)
## remove the schema
prompt = ChatPromptTemplate.from_messages([
    ("system", "Classify into one of: weather, chart, database, other, ERD. Return JSON with key intent."),
    ("human", "{input}")
])



############ start of declare custom tools for schema inspection  ############
@tool
def _get_all_schemas():
    """  list down all the schemas in the database and return as list of strings for user to understand what columns to query for in the table  """
    query = """
    SELECT n.nspname AS schema_name
    FROM pg_catalog.pg_namespace n
    WHERE n.nspname NOT LIKE 'pg_%'
      AND n.nspname <> 'information_schema'
    ORDER BY schema_name;
    """
    rows = db_._execute(query, fetch="all")
    return [row["schema_name"] for row in rows]

@tool
def _get_tables_in_schema(schema_name):
    """ list down all the tables in the given schema and return as list of strings for user to understand what columns to query for in the table """
    query = f"""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = '{schema_name}';
    """
    rows = db_._execute(query, fetch="all")
    return [row["table_name"] for row in rows]

@tool
def _get_columns_in_table(schema_name, table_name):
    """ list down all the columns in the given table and return as list of strings for user to understand what columns to query for in the table """
    query = f"""
    SELECT column_name , data_type
    FROM information_schema.columns
    WHERE table_schema = '{schema_name}' AND table_name = '{table_name}';
    """
    rows = db_._execute(query, fetch="all")
    return [(row["column_name"], row["data_type"]) for row in rows]

@tool
def _get_schema_for_table(table_name):
    """ given a table name, return the schema.table_name it belongs to for user to understand which schema to query for tables and columns """
    query = f"""
    SELECT  table_schema || '.' || table_name  AS full_table_name
    FROM information_schema.tables
    WHERE table_name = '{table_name}';
    """
    rows = db_._execute(query, fetch="all")
    return [row["full_table_name"] for row in rows]


@tool
def _create_chart_from_query(sql_query):
    """ given a sql query, run the query and create chart using matplotlib or seaborn and return the image in fig object format """


    df = pd.DataFrame(db_._execute(sql_query, fetch="all"))
    if df.empty:
        return "Query returned no results, cannot create chart."
    column_array = df.columns.values
    flag=1
    is_chart=True
    if flag ==1 :
        # fig, ax = plt.subplots(figsize=(8, 5))
        # sns.barplot(data=df, x=column_array[0], y=column_array[1], ax=ax)
        # my_plot = sns.barplot(data=df, x=df.columns[0], y=df.columns[1], ax=ax)

        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(data=df, x=df.columns[0], y=df.columns[1], ax=ax)
        plt.tight_layout()


        ax.set_title("Top 10 Happiest Countries (2019)")
        print("m" * 80)
        print(fig)
        print("m" * 80)
        return ({"role": "assistant", "is_chart": True, "is_erd": False, "chart": fig})
    else:
        # For simplicity, let's assume the user wants a bar plot of the first two columns
        plt.figure(figsize=(4, 6))
        sns.barplot(x=df.columns[0], y=df.columns[1], data=df)
        plt.xticks(rotation=45)
        plt.tight_layout()

        buf = io.BytesIO()
        # plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        # buf.seek(0)
        # img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        # print("n" * 80)
        # print(img_base64)
        # print("n" * 80)      
        # return f"data:image/png;base64,{img_base64}"  ##return img_base64
        return buf.getvalue()
    



@tool
def _get_data_for_erd(schema_name, table_name):
    """ given a schema name, return the data needed to create an ERD diagram for the tables in the schema to help user
      understand the relationships between the tables and how to query for them """
    query = f"""
SELECT 
    cols.table_schema, 
    cols.table_name, 
    cols.column_name, 
    cols.data_type,

    CASE 
        WHEN pk.column_name IS NOT NULL THEN 'PK' 
        ELSE '' 
    END AS primary_key,

    CASE 
        WHEN fk.column_name IS NOT NULL THEN 'FK' 
        ELSE '' 
    END AS foreign_key,

    pg_catalog.col_description(c.oid, cols.ordinal_position::int) AS column_description,
    fk.table_schema, 
    fk.table_name, 
    fk.column_name
FROM 
    information_schema.columns cols
JOIN 
    pg_catalog.pg_class c ON c.relname = cols.table_name
JOIN 
    pg_catalog.pg_namespace n ON n.oid = c.relnamespace AND n.nspname = cols.table_schema

LEFT JOIN (
    SELECT kcu.table_schema, kcu.table_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu 
      ON tc.constraint_name = kcu.constraint_name 
      AND tc.table_schema = kcu.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY'
) pk ON cols.table_schema = pk.table_schema 
    AND cols.table_name = pk.table_name 
    AND cols.column_name = pk.column_name

LEFT JOIN (
    SELECT kcu.table_schema, kcu.table_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu 
      ON tc.constraint_name = kcu.constraint_name 
      AND tc.table_schema = kcu.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
) fk ON cols.table_schema = fk.table_schema 
    AND cols.table_name = fk.table_name 
    AND cols.column_name = fk.column_name
WHERE 
    cols.table_schema NOT IN ('information_schema', 'pg_catalog')
ORDER BY 
    cols.table_schema, cols.table_name, cols.ordinal_position;
    """
    rows = db_._execute(query, fetch="all")
    return [dict(row) for row in rows]    
############ End of declare custom tools for schema inspection  ############
 






erd_template = """
{
  "database": "database_name",
  "tables": [
    {
      "table": "table_name",
      "columns": [
        {"name": "column1", "type": "int"},
        {"name": "column2", "type": "int"},
        {"name": "column3", "type": "date"}
      ],
      "primary_key": ["column1"],
      "foreign_keys": [
        {
          "column": "column2",
          "references_table": "referenced_table",
          "references_column": "referenced_column"
        }
      ]
    }
  ]
}
"""

tools = toolkit.get_tools()

system_prompt = f"""
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct {db_.dialect} query to run,
then look at the results of the query and return the answer.
You MUST double check your query before executing it.
DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.).
To start, ALWAYS list tables, then inspect relevant schemas.
use chat history to find out what user is asking for and what they have asked for in the past to decide which tool to use and what query to run.
"""

system_prompt = f"""
You are an agent designed to interact with a SQL database.
Use {db_.dialect} syntax.
Return ERD data in JSON format like this:

{erd_template}
NOTE: Convert ERD JSON → Mermaid Diagram syntax like this:
erDiagram

CUSTOMERS {{
 int customer_id
 varchar name
 varchar email
}}

ORDERS {{
 int order_id
 int customer_id
 date order_date
}}

CUSTOMERS ||--o{{ ORDERS : customer_id
"""

all_tools = tools + [_get_all_schemas, _get_tables_in_schema, _get_columns_in_table ,_get_schema_for_table 
                     , _create_chart_from_query ,_get_data_for_erd]

checkpointer = InMemorySaver()

agent_executor = create_agent(  
    model=llm_client,
    tools=all_tools,
    system_prompt=system_prompt ,
    checkpointer=checkpointer,  # enables thread-level memory
    # debug = True ,
)


def get_schema(state):
    # host = "localhost"
    # database = "postgres"
    # user = "user1"
    # password = "user1"
    # port = "5432"    
    # schem_cls = schema_details( host, database, user, password, port )
    # state.schema_detail = schem_cls.get_main()
    state.schema_detail = schem_cls.get_main2()  ## ,config=config_memory
    return state

def call_azure_openai(state) -> str:
    """
    Convert Taipy messages -> Azure OpenAI chat messages,
    call the model, and return the assistant reply text.
    """
    print("Preparing messages for Azure OpenAI...")
    # print("Preparing messages for Azure OpenAI...")
    # print(" state:", state.messages)
    # System prompt first
    messages_payload.append({
        "role": "system",
        "content": "You are a helpful AI assistant."
    })
    # print("m" * 120)
    # for _mid, content, sender in messages:
    #     print("message from", sender , " content:", content)
    # print("m" * 120)
    # # Map our (id, content, sender_id) to OpenAI roles
    # for _mid, content, sender in messages:
    #     # print("message from", sender , " content:", content)
    #     role = "assistant" if sender == "assistant" else "user"
    #     messages_payload.append({"role": role, "content": content})
    # llm_client = MainClass().get_llm_client()
    
    # completion = llm_client.chat.completions.create(
    #     model=AZURE_OPENAI_DEPLOYMENT,
    #     messages=messages_payload,
    #     temperature=0.7,
    # )
    completion = llm_client.invoke(messages_payload ,config=config_memory)
    # print("-" * 80)
    # print("Azure OpenAI completion:", completion)
    # print("-" * 80)    
    return completion.content  ##choices[0].message.content  # type: ignore


def get_intent(state, user_input) -> str:
    """
    Get the intent of the user input.
    """
    print("Getting intent...")

    messages = prompt.format_messages(input=user_input)
    out: IntentOut = intent_llm.invoke(messages)
    return out.intent




def get_database_info(state, user_input: str) -> str:
    print("inside get_database_info")

    text = (user_input or "").strip()
    text_lc = text.lower()

    # Special route: list schemas (but not tables)
    wants_schema_list = ("schema" in text_lc) and ("list" in text_lc) and ("table" not in text_lc)

    result = agent_executor.invoke(
        {"messages": [{"role": "user", "content": text}]}, config=config_memory
        )

    # result = agent_executor.invoke({"messages": st.session_state.messages + [{"role": "user", "content": user_input}]}, config=config_memory)     
    print("get_database_info -> Preparing messages for Azure OpenAI...", result["messages"][-1].content)

    # Expect state.messages = [(id, content, sender), ...]
    history = getattr(state, "messages", []) or []

    # messages_payload = [{"role": "system", "content": system_prompt}]
    # messages_payload += [
    #     {"role": ("assistant" if sender == "assistant" else "user"), "content": content}
    #     for _mid, content, sender in history
    #     if content  # skip empty
    # ]
    return result["messages"][-1].content

# Extract the query

def extract_sql_query(result_dict: dict) -> str:
    """Extract SQL query from LangGraph result messages"""
    messages = result_dict.get('messages', [])
    
    # Find the last AIMessage that contains content (not empty tool calls)
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content.strip()
            # Skip empty content (tool call requests have empty content)
            if content and not content.startswith('```'):
                return content
            # Handle markdown code blocks
            elif content.startswith('```sql'):
                return content.replace('```sql', '').replace('```', '').strip()
            elif content.startswith('```'):
                return content.replace('```', '').strip()
    
    return None


import re
from typing import Optional

def extract_query_advanced(result_dict: dict) -> Optional[str]:
    """
    Advanced extraction handling various formats:
    - Plain SQL
    - Markdown code blocks
    - Tool call arguments
    """
    messages = result_dict.get('messages', [])
    
    # Strategy 1: Last AIMessage with content
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content.strip()
            
            # Extract from markdown code blocks
            if '```sql' in content:
                match = re.search(r'```sql\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    return match.group(1).strip()
            
            # Extract from generic code blocks
            if content.startswith('```'):
                return content.strip('`').strip()
            
            # Plain content (your case)
            if content and not content.startswith('<'):
                return content
    
    # Strategy 2: Check tool calls for query
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tool_call in msg.tool_calls:
                args = tool_call.get('args', {})
                if 'query' in args:
                    return args['query']
    
    # Strategy 3: Check ToolMessage for query checker results
    for msg in messages:
        if isinstance(msg, ToolMessage) and 'sql' in msg.name.lower():
            content = msg.content.strip()
            if content.startswith('```sql'):
                match = re.search(r'```sql\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    return match.group(1).strip()
    
    return None


def get_chart_type(state, user_input):

    res = llm_client.invoke([
        HumanMessage(content=f"""
        1. You are a helpful assistant that extracts the chart type from user input.
        2. You will be given a question and must extract the visualization type from it.                         
        3. Respond ONLY with the visualization type. If no visualization is found, respond with an empty string.
        4. The visualization types can be: 'bar', 'line', 'scatter', 'pie', 'histogram', 'boxplot', 'heatmap', 'area', 'donut', 'radar', 'funnel', 'treemap', or 'wordcloud'.
        5. If the question does not specify a visualization type, respond with an empty string  
        Question: {user_input}
        """)
        ])
    chart_name = res.content.strip()
    # state["chart_type"] = chart_name
    print(f"🚨 get_chart_type DEBUG: state = {chart_name}")
   
    return {"chart_type" :chart_name }

    # text = (state.user_input or "").strip()
    # messages = prompt.format_messages(input=text)
    # out: IntentOut = intent_llm.invoke(messages)
    # return out.intent


def get_chart(state ,user_input ) :

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
    print("get_chart  -> Preparing messages for Azure OpenAI...")
    text = (user_input or "").strip() + '  and return ONLY QUERY'
    print("claiing the invoke of agent_executor with text:")
    intent_chart_type  = get_chart_type(state, state.user_input)
    print("o" * 80)
    print("Intent for chart type:", intent_chart_type["chart_type"])
    print("o" * 80)    
    result = agent_executor.invoke(
        {"messages": [{"role": "user", "content": text}]}, config=config_memory
        )
    
    # result = agent_executor.invoke({"messages": st.session_state.messages + [{"role": "user", "content": text}]}, config=config_memory)     

    # print("lllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllll")
    # print(" return value of get_chart is ::::: ", result )
    # raw= result["messages"][-1].content

    # sql_query = raw.split("```sql")[1].split("```")[0]  ## re.search(r"json\s*(.*?)\s*", raw, re.DOTALL).group()
    # sql_query = get_final_sql(result)
    # Usage
    sql_query = extract_sql_query(result)
    print(f"Extracted SQL: {sql_query}")    
    # print("Extracted SQL query:", sql_query)
    # print("vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv")    
    rows = db_._execute(sql_query, fetch="all")
    df = pd.DataFrame(rows)

  
    state.is_chart=True

    print("isinstance(result, dict)  -- >   Creating chart from query result...")
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(10, 6))  

    sns.barplot(x=df.columns[0], y=df.columns[1], data=df)
    if 'pie' in intent_chart_type["chart_type"] or 'donut' in intent_chart_type["chart_type"]:
        fig = chart_funcs[intent_chart_type["chart_type"]](df, names=df.columns[0], values=df.columns[1] , hole=0.3 if 'donut' in intent_chart_type["chart_type"] else 0)  
    elif 'radar' in intent_chart_type["chart_type"]:
        fig = chart_funcs[intent_chart_type["chart_type"]](df, r=df.columns[1], theta=df.columns[0])  
    else:
        fig = chart_funcs[intent_chart_type["chart_type"]](df,
                    x=df.columns[0],
                    y=df.columns[1] 
                    #  size="TotalOpeningAmount", # Make marker size proportional to population
                    #  color="CUST_COUNTRY",      # Color markers by city
                    #  hover_name="CUST_COUNTRY", # Show city name on hover
                    , title=f"{df.columns[0]}  vs. {df.columns[1]}"
                    )

    # buf = io.BytesIO()
    # plt.tight_layout()        
    # fig.savefig(buf, format='png' ) ##, dpi=150, bbox_inches='tight')
    # buf.seek(0)
    # img = base64.b64encode(buf.read()).decode()
    # plt.close(fig)  
    # state.image_data= "data:image/png;base64," + img       ##"data:image/png;base64," + img
    # return "data:image/png;base64," + img
    return ({"role": "assistant", "is_chart": True, "is_erd": False, "chart": fig})
        


    # return (result["messages"][-2].content)
def extract_mermaid(text: str) -> str:
    pattern = r"```mermaid\s*(.*?)```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1).strip()
    return None

def create_erd(state ,user_input ) :
    result = agent_executor.invoke(
            {"messages": [{"role": "user", "content": user_input}]}, config=config_memory   
            )
    first_message_content = result["messages"][-1].content.splitlines()[0]
    erDiagram = extract_mermaid(result["messages"][-1].content)
    return {"role": "assistant", "is_chart": False ,"is_erd": True, "erDiagram": erDiagram}

def get_all_schema(state):

    # if "select" in state.user_input.lower() or "list" in state.user_input.lower():
    #     state.schema_name=""
    #     return "The user is asking for schema information."
    # else:
    query = """
    SELECT n.nspname AS schema_name
    FROM pg_catalog.pg_namespace n
    WHERE n.nspname NOT LIKE 'pg_%'
    AND n.nspname <> 'information_schema'
    ORDER BY schema_name;
    """    
    DATABASE_URI = schem_cls.DATABASE_URI
    db_ = schem_cls.get_db_conn()  ##  SQLDatabase.from_uri(DATABASE_URI)  ##schem_cls.get_db_conn()
    result = db_._execute(query)
    schema_list = [row["schema_name"] for row in result]
    return f"Available schemas: {', '.join(schema_list)}"

def messages_for_model(state,max_turns: int = 20):
    system = st.session_state.messages[:1]
    rest = st.session_state.messages[1:]
    return system + rest[-max_turns:]
    
def router(state ,user_input):
    """
    Decide whether to call Azure OpenAI or the add tool
    based on the user input.
    """
    print("Determining intent...")
    intent_text =get_intent(state, state.user_input)
    print("Intent text:", intent_text)
    # state.messages_for_model = messages_for_model(state)#

    match intent_text:
        case "text" | "other":
            print("Calling Azure OpenAI...")
            return call_azure_openai(state)
        case "code":
            return "Here is some code."
        case "chart":
            print("Calling get_chart function ...")
            return get_chart(state, state.user_input)
        case "database":
            print("Calling get_database_info function ...")
            return get_database_info(state, state.user_input)
        case "ERD":
            print("Calling get_data_for_erd function ...")
            return create_erd(state, state.user_input)
        #_get_data_for_erd(state.schema_name, None)  ## for simplicity, we are passing table_name as None to get the ERD for the entire schema. This can be enhanced to extract table_name from user_input if needed.
        case "schema":
            print("Calling get_schema function ...")
            return get_all_schema(state)
        case _:
            return f"intent is {intent_text}"
        
    # if intent_text =="text" or intent_text =="other":
    #     print("Calling Azure OpenAI...")
    #     return call_azure_openai(state)
    # elif intent_text =="code":
    #     return "Here is some code."
    # elif intent_text =="chart"  :
    #     return get_chart(state ,user_input)  # "Result of addition is from database."
    # elif intent_text =="database" :
    #     return get_database_info(state ,user_input)  # "Result of addition is from database."    
    # else:
    #     return f"intent is {intent_text}"
def _router_worker(state, user_input: str):
    # IMPORTANT: no state access here (runs in background thread)
    return router(state, user_input)  # or router(user_input) depending on your signature

def _on_router_done(state, assistant_reply: str):
    # UI thread update (safe)
    state.thinking = False
    # notify(state, "success", "Response received!")

    state.msg_seq += 1
    assistant_msg = (str(state.msg_seq), assistant_reply, "assistant")
    state.messages = [*state.messages, assistant_msg]

    state.current_prompt = ""  # clear textarea



def evaluate(state, user_input):
    print("Evaluating...")

    # args = (payload or {}).get("args") or []
    # user_input = args[2] if len(args) > 2 else None
    # if not user_input:
    #     return

    print("*" * 80)
    print("User input:", user_input)

    state.thinking = True
    # notify(state, "info", "Thinking...")

    state.user_input = user_input



    # 2) Compute assistant reply
    print("Y" * 80)    
    print("calling router...")
    assistant_reply = router(state, user_input)

    print(assistant_reply)
    if isinstance(assistant_reply, dict) and assistant_reply.get("is_chart"):
        # print("Received chart data in assistant reply.")
        # print(assistant_reply)
        return assistant_reply  # Return the chart data to be rendered by the UI
    elif isinstance(assistant_reply, dict) and assistant_reply.get("is_erd"):
        # print("Received ERD data in assistant reply.")
        # print(assistant_reply)
        return assistant_reply  # Return the ERD data to be rendered by the UI
    else:
        # print("Received assistant reply:", assistant_reply[:100])  # print first 100 chars for brevity
        pass
    print("Y" * 80)
    state.thinking = False


    # 4) Clear input
    state.current_prompt = ""
    state.is_chart=False
    state.image_data=None
    state.is_erd=False
    return assistant_reply


