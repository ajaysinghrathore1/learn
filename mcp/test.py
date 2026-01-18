import asyncio
from mcp_sql_client import m_SQL_Client
from fastmcp import Client
import re
import pandas as pd
from io import StringIO  # Add this import

from config import Settings, get_settings
from typing import Any, Dict, List, Type
from mcp import ClientSession, types
host = m_SQL_Client()

async def main():
    # agent = await host._get_agent()

    # print(type(agent))

    question = "list top 5 customer from country Germany"
    # question = "delete the customer whos id is  ANATR"
    # question = "delete the customer "
    # question = "update the customers of customers table from country maxico to India "    
    # question = "I like to create a  bar chart, show me the right combination of columns from the schema"        


    response = await host.llm_generate_sql(question)
    # print("0" * 80)    
    # print(response)
    # print("0" * 80)
    # print("\n\n\n")

    if response.structured_content["result"] =='[]':
        print(response.meta)
    else:
        try:
            count3=len(response["messages"])        
            print(response["messages"][count3 -1].content)  
        except Exception as e :
            json_data = response.content[0].text


            # print(json_data)
            #3. Convert back to a DataFrame
            df = pd.read_json(StringIO(json_data))
            print("9" * 80 )
            # 4. Print as a single-line formatted DataFrame
            pd.set_option('display.expand_frame_repr', False)
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 1000)
            print(df.to_string(index=False))
            print("9" * 80 )
    #             
    # print(print(response["messages"][1].content ))  ###AIMessage)

 


asyncio.run(main())      

#     def mcp_tool_to_openai(tool: types.Tool) -> Dict[str, Any]:
#         """Convert MCP Tool -> OpenAI 'tools' schema (function calling)."""
#         return {
#             "type": "function",
#             "function": {
#                 "name": tool.name,
#                 "description": tool.description or "",
#                 # MCP uses JSON Schema for inputSchema; OpenAI tools 'parameters' is also JSON Schema.
#                 "parameters": tool.inputSchema or {"type": "object", "properties": {}},
#             },
#         }
    

#     # async with Client("http://127.0.0.1:8085/mcp" , timeout= 80) as client:
#     #     tools_resp = await client.list_tools()
#     #     print(tools_resp)
#     #     for tool in tools_resp:
#     #         print(tool.name)
#     #         print(tool.description)
#     #         openai_tools = mcp_tool_to_openai(tool) 


#     #     openai_tools = [mcp_tool_to_openai(t) for t in tools_resp]
#     #     print(openai_tools)

#     #     print("*" * 80)
#     #     print(type(openai_tools))
#         # await client.initialize()
#         # result = await client.call_tool("top_customers", {"country": "Mexico", "limit": 5})
#         # result = asyncio.wait_for( client.call_tool("schema_details" ,
#         #                              {'user_query':'list top 5 customer from country usa'},
      
#         #                             timeout=180,
#         #                             raise_on_error=False,
#         #                             )
#         #                         )



#     # print(await host.get_mcp_tools())
#     print("\n\n\n")

#     # question = "list top 5 customer from country Mexico, convert the output to table or dataframe"
    
#     # print(await host.llm_generate_sql(question))
#     # response = await host.llm_generate_sql(" list customer from usa")
#     # llm = host._get_model()          # llm is an AzureChatOpenAI object
#     # resp = llm.invoke("hello")       # returns an AIMessage (LangChain message object)
#     # print(resp)

#     agent = host._get_agent()

#     print(type(agent))
#     question = "list top 5 customer from country Mexico, convert the output to table or dataframe"

#     result = agent.invoke(
#         {"messages": [{"role": "user", "content": question}]}
#     )

#     # # Same output style as your stream loop:
#     # out = result["messages"][-1] ##.pretty_print()
#     # print(type(out))
#     # print(out.content)


#     # print(response)

#     # settings = Settings()
#     # print(settings.app_name)
#     # print(settings.Driver)


# asyncio.run(main())    