# host.py
# Azure OpenAI (LLM) + MCP Server (tools) host/client
#
# pip install openai "mcp[cli]" pydantic
#
# Env vars (example):
#   export AZURE_OPENAI_API_KEY="..."
#   export AZURE_OPENAI_BASE_URL="https://YOUR-RESOURCE-NAME.openai.azure.com/openai/v1/"
#   export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"   # your *deployment name*
#   export MCP_URL="http://127.0.0.1:8085/mcp"
#
# Run:
#   python host.py

from __future__ import annotations
import asyncio
import json
import os
import re
from typing import Any, Dict ,Optional
import traceback
import tracemalloc
tracemalloc.start(25)

from fastmcp import Client
from config import Settings, get_settings

from langchain_community.utilities.sql_database import SQLDatabase
from langchain_openai.chat_models.azure import AzureChatOpenAI
from langchain_community.agent_toolkits import create_sql_agent, SQLDatabaseToolkit
from langchain.agents import create_agent   ### declare agent for query and llm
from langchain_core.messages import filter_messages, ToolMessage
from langchain_core.messages import AIMessage
from openai import OpenAI

class m_SQL_Client():

    def __init__(self, url: str = "http://127.0.0.1:8085/mcp" , default_rows_return : int = 5):
        # IMPORTANT: no trailing slash
        self.url = url
        self.default_rows_return = default_rows_return
        # ====== GLOBAL CACHES ======
        self._ENGINE = None
        self._DB: Optional[SQLDatabase] = None
        self._LLM: Optional[AzureChatOpenAI] = None
        self._AGENT: Any = None
        self._get_model()
        self._database_Con()
        # self._get_agent()


    def get_setting(settings: Settings ) -> dict:
        settings = Settings()
        print(settings.app_name)
        print(settings.mssql_conn) 

    async def get_mcp_tools(self ,  timeout_s: int = 180) :
         async with Client("http://127.0.0.1:8085/mcp" , timeout= 80) as client:
            tools_resp = await client.list_tools()
            openai_tools = [mcp_tool_to_openai(t) for t in tools_resp]
            return (openai_tools)




    def _get_model(self):
        """ get the LLm model """
       
        if self._LLM is not None:
            return self._LLM
        AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
        AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
        AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

        if not (AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY and AZURE_OPENAI_API_VERSION):
            raise RuntimeError("Missing Azure env vars: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_API_VERSION")

        self._LLM = AzureChatOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            openai_api_version=AZURE_OPENAI_API_VERSION,
            deployment_name=AZURE_OPENAI_DEPLOYMENT,
            # model_name=AZURE_OPENAI_DEPLOYMENT,
            openai_api_key=AZURE_OPENAI_API_KEY,
            openai_api_type="azure",
            temperature=0.0,   # reduces parser drift
            timeout=60.0,
            max_retries=2,
        )
        return self._LLM

    def _database_Con(self):
        if self._DB is not None:
            return self._DB
                
        database = "northwind"  #"demo"
        # database="AdventureWorks"
        table = "dbo.orders"
        # table = "SalesLT.Product"
        username = "ajay"
        password = "callme123"
        DB_SERVER  = r"localhost:1433"

        conn_str = f"mssql+pyodbc://{username}:{password}@{DB_SERVER }/{database}?driver=ODBC+Driver+17+for+SQL+Server"

        self._DB = SQLDatabase.from_uri(conn_str)    
        return self._DB

    async def _get_agent(self):
        ## declare toolkit and tool 
        if self._AGENT is not None:
            return self._AGENT
        
        Azuremodel = self._get_model()
        db_conn = self._database_Con()
        toolkit = SQLDatabaseToolkit(db=db_conn, llm=Azuremodel)
        tools = toolkit.get_tools() 
        openai_tools = await self.get_mcp_tools()
        # print(" prompt" * 5)
        dialect=db_conn.dialect
        # print(f"dialect :  {dialect}")
        system_prompt2= await self.get_get_query_prompt(dialect , self.default_rows_return )
        # aa= system_prompt2.messages[0].content
        # print(json.loads(system_prompt2.messages[0].content.text)["system_prompt"])
        # print(" prompt" * 5)        
        system_prompt = json.loads(system_prompt2.messages[0].content.text)["system_prompt"]   ###self._get_system_prompt(db_conn)
        # print(system_prompt)
        prefix = """
        You are a helpful assistant that can answer questions using a Microsoft SQL Server database.

        Rules:
        - Use the database tools when the user asks about data that likely exists in the DB.
        - If the question is NOT answerable from the database (e.g., general knowledge), say it’s out of DB scope
        and answer normally without inventing database results.
        - If a query returns 0 rows, say so and suggest what to check (filters, table, spelling).
        """.strip()

        self._AGENT = create_agent(  ### TypeError: object CompiledStateGraph can't be used in 'await' expression
            tools = tools,
            model =Azuremodel,
            system_prompt=system_prompt,
            # top_k= 10 # Limits results to 5
            )
        
        # self._AGENT = create_sql_agent(
        #     llm=Azuremodel,
        #     toolkit=toolkit,
        #     # Extra tools (MCP tools etc.)
        #     # extra_tools=Azuremodel   ,  #openai_tools,
        #     # Agent behavior
        #     verbose=False,              # prints tool calls / reasoning steps (useful for debugging)
        #     top_k=5,                   # how many rows to show by default when listing results
        #     # Prompting
        #     prefix=prefix,

        #     # Agent type:
        #     # - "openai-tools" (or similar) for tool-calling chat models (recommended for AzureChatOpenAI)
        #     # - "zero-shot-react-description" for older non-tool-calling setups
        #     agent_type="openai-tools",
        # )

        
        return self._AGENT



    def _get_system_prompt(self ,db):

        # If you get an error while  executing a query, rewrite the query and try again.

        system_prompt = """
        You are an agent designed to interact with a SQL database.
        Given an input question, create a syntactically correct {dialect} query,
        RETURN ONLY THE  SQL STATEMENT ONLY with limiting scope most {top_k}.

        Never query for all the columns from a specific table,
        only ask for the relevant columns given the question.

        You MUST double check your query before responding back ONLY QUERY. 

        Make any DML statements (INSERT, UPDATE, DELETE ) to the
        database ONLY if a filter condition provided by User. If no Filter condition, ask user or suggest the filter condition.

        To start you should ALWAYS look at the tables in the database to see what you
        can query. Do NOT skip this step.

        Note: suggest 3-5 distinct user input base on data.
        """.format(
            dialect=db.dialect,
            top_k=5,
        )
        return system_prompt


    def get_type_of_query(self, sql: str) ->  str | None:
    # def sql_type_cte_aware(sql: str) -> str | None:
        if not sql:
            return None

        # strip leading comments
        s = re.sub(r"^\s*(--.*\n|/\*.*?\*/\s*)*", "", sql, flags=re.DOTALL | re.MULTILINE).lstrip()

        # if it starts with WITH, skip CTE block(s) and find the next verb
        if s[:4].upper() == "WITH":
            # crude but practical: find first SELECT/INSERT/UPDATE/DELETE/MERGE after WITH
            m = re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE)\b", s, flags=re.IGNORECASE)
            return m.group(1).upper() if m else "WITH"

        m = re.match(r"([A-Za-z]+)", s)
        return m.group(1).upper() if m else None

    def get_last_query(self,result, tool_name="sql_db_query") -> str | None:
        for i, m in enumerate(result["messages"], 1):
            mtype = type(m).__name__
            content = (m.content or "").replace("\n", "\\n")  # keep it one-line
            if '```sql' in content:
                content=content.replace('```sql','')
                content=content.replace('```','')
                content=content.replace('\\n',' ')
                return content

        # for m in reversed(result["messages"]):
        #     if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
        #         for tc in m.tool_calls:
        #             if tc.get("name") == tool_name:
        #                 return (tc.get("args") or {}).get("query")
        return None

    async def get_response(self,question : str) -> dict:
        agent = self._get_agent()
        result = await self._agent.invoke(
        {"messages": [{"role": "user", "content": question}]}
        )
        return result



    async def llm_generate_sql(self, user_prompt) :
        agent= await self._get_agent()

        ### using create_agent 
        response =  await agent.ainvoke(
            {"messages": [
                #  {"role": "system", "content": self._get_system_prompt(self._DB )},
                {"role": "user", "content": user_prompt}]}
            )
        ### using create_sql_agent 
        # response =  await agent.ainvoke({"input": user_prompt})
        # print("1" * 80)  
        # print(response)
        count_list=len(response["messages"])
        ai_response = response["messages"][count_list -1].content
        # print(ai_response)
        
        # print("1" * 80)  
        query = self.get_last_query(response)
        query_type = self.get_type_of_query(query)
        print('query_type', query_type , 'sql' ,query)
        if query_type=='SELECT' or query_type=='DELETE' :
            resp_out = await self.get_data(query)
            # print("7" * 80)
            # print(resp_out)
            # print("7" * 80)     
            if (resp_out.structured_content["result"]) =='[]' :  ## if no row return --, structured_content={'result': '[]'}, meta=None, data='[]', is_error=False)
                # print(ai_response)
                resp_out.meta =ai_response
                # print(resp_out)
                return  resp_out 
            else:
                return resp_out
        # return {'query_type': query_type , 'sql' :response}  ##response["messages"][-1].content
        return response

    async def get_data(self, sql : str) -> str | None:
        async with Client("http://127.0.0.1:8085/mcp" , timeout= 80) as client:
            response = await client.call_tool('get_table_data', {'sql' :sql})
        return response

    async def get_get_query_prompt(self, db_dialect : str , top_k : int ) -> str | None:
        async with Client("http://127.0.0.1:8085/mcp" , timeout= 80) as client:
            response = await client.get_prompt('get_query_prompt', {'db_dialect' : db_dialect , 'top_rows' : top_k })

        return response



# Optional: block write tools behind a confirmation prompt
WRITE_TOOLS = {
    "add_row",
    "update_row",
    "delete_row",
    "execute_sql_write",
    "execute_sql",  # keep/remove depending on how you split read vs write
}


def mcp_tool_to_openai(tool: types.Tool) -> Dict[str, Any]:
    """Convert MCP Tool -> OpenAI 'tools' schema (function calling)."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            # MCP uses JSON Schema for inputSchema; OpenAI tools 'parameters' is also JSON Schema.
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


def calltoolresult_to_text(result: types.CallToolResult) -> str:
    """Render MCP CallToolResult into a string we can feed back to the model."""
    chunks: List[str] = []

    # Prefer structuredContent when present
    structured = getattr(result, "structuredContent", None)
    if structured:
        chunks.append(json.dumps(structured, ensure_ascii=False))

    for c in result.content or []:
        if isinstance(c, types.TextContent):
            chunks.append(c.text)
        elif isinstance(c, types.EmbeddedResource):
            # Minimal rendering; customize if you want to inline the resource contents.
            chunks.append(f"[embedded resource: {c.resource.uri}]")
        elif isinstance(c, types.ImageContent):
            chunks.append(f"[image {c.mimeType}, {len(c.data)} bytes]")
        else:
            chunks.append(str(c))

    text = "\n".join(x for x in chunks if x).strip()
    if not text:
        text = "(empty tool result)"
    if result.isError:
        text = "TOOL_ERROR:\n" + text
    return text


def assistant_message_with_tool_calls(model_msg) -> Dict[str, Any]:
    """Create a messages[] item that preserves tool_calls for the next model turn."""
    tool_calls = []
    for tc in (model_msg.tool_calls or []):
        tool_calls.append(
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
        )
    return {
        "role": "assistant",
        "content": model_msg.content or "",
        "tool_calls": tool_calls,
    }


async def chat_loop(mcp_url: str) -> None:
    # Azure OpenAI via OpenAI-compatible /openai/v1/ base_url
    client = OpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        base_url=os.environ["AZURE_OPENAI_BASE_URL"],  # e.g. https://<resource>.openai.azure.com/openai/v1/
    )
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]  # deployment name (Azure requirement)

    async with streamable_http_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()

            tools_resp = await mcp.list_tools()
            mcp_tools = tools_resp.tools
            openai_tools = [mcp_tool_to_openai(t) for t in mcp_tools]

            print("Connected to MCP:", mcp_url)
            print("MCP tools:", [t.name for t in mcp_tools])

            messages: List[Dict[str, Any]] = [
                {
                    "role": "system",
                    "content": (
                        "You are a SQL Server assistant. Use tools when needed.\n"
                        "If a request modifies data, ask for confirmation (or call a dedicated write tool)."
                    ),
                }
            ]

            while True:
                user_text = input("\nYou: ").strip()
                if not user_text:
                    continue
                if user_text.lower() in {"exit", "quit"}:
                    break

                messages.append({"role": "user", "content": user_text})

                # Keep resolving tool calls until the model returns a final answer
                while True:
                    resp = client.chat.completions.create(
                        model=deployment,
                        messages=messages,
                        tools=openai_tools,
                        tool_choice="auto",
                    )
                    msg = resp.choices[0].message

                    if msg.tool_calls:
                        # 1) store the assistant message (with tool_calls)
                        messages.append(assistant_message_with_tool_calls(msg))

                        # 2) execute each tool call and append tool results
                        for tc in msg.tool_calls:
                            tool_name = tc.function.name
                            raw_args = tc.function.arguments or "{}"
                            try:
                                tool_args = json.loads(raw_args)
                                if not isinstance(tool_args, dict):
                                    tool_args = {"_args": tool_args}
                            except json.JSONDecodeError:
                                tool_args = {"_raw_arguments": raw_args}

                            if tool_name in WRITE_TOOLS:
                                print(f"\n⚠️ WRITE tool requested: {tool_name}({tool_args})")
                                ok = input("Execute? (y/N): ").strip().lower() == "y"
                                if not ok:
                                    messages.append(
                                        {
                                            "role": "tool",
                                            "tool_call_id": tc.id,
                                            "content": "User denied execution.",
                                        }
                                    )
                                    continue

                            result = await mcp.call_tool(tool_name, arguments=tool_args)
                            tool_text = calltoolresult_to_text(result)

                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": tool_text,
                                }
                            )

                        # loop again to let the model incorporate the tool outputs
                        continue

                    # Final natural language response
                    final = msg.content or ""
                    messages.append({"role": "assistant", "content": final})
                    print("\nAssistant:", final)
                    break


if __name__ == "__main__":
    asyncio.run(chat_loop(os.getenv("MCP_URL", "http://127.0.0.1:8085/mcp")))
