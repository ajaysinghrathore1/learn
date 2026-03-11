import os
import re
import json
import pandas as pd
from jsonmerge import merge
import sys
from pathlib import Path

# get project root
project_root = Path.cwd().parent
sys.path.append(str(project_root))
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_openai.chat_models.azure import AzureChatOpenAI
from langchain.agents import create_agent
from common.main_class import AZURE_OPENAI_DEPLOYMENT, MainClass
from langgraph.checkpoint.memory import InMemorySaver
from io import StringIO
import numpy as np

# Use InMemorySaver for a simple, in-memory checkpointer. 
# For production, you'd use a database-backed checkpointer (e.g., PostgresSaver).
checkpointer = InMemorySaver()

class schema_details():
    def __init__(self, host, database, user, password, port):
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.port = port
        self.system_prompt = """You are a helpful assistant for SQL database queries..."""
        self.DATABASE_URI = f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    def get_db_conn(self):
        # DATABASE_URI = f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        db = SQLDatabase.from_uri(self.DATABASE_URI)
        return db

    def _get_llm(self):

        llm_client = MainClass().get_llm_client()

        completion = llm_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=self.system_prompt,
            temperature=0.7,
        )        
        return llm_client
    


    def extract_json_block(self,text: str) -> str:
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if not m:
            raise ValueError("No ```json ... ``` block found in LLM output")
        return m.group(1)

    def get_agent(self, system_prompt =None ,schema_name ="public"):
        db_local = SQLDatabase.from_uri(self.DATABASE_URI, schema=schema_name)
        if system_prompt is None:
            system_prompt = self.system_prompt
        toolkit = SQLDatabaseToolkit(db=db_local, llm=MainClass().get_llm_client()  ) ##self._get_llm())
        tools = toolkit.get_tools()

        agent = create_agent(
            model=MainClass().get_llm_client()  , #self._get_llm(),
            tools=tools,
            system_prompt=system_prompt,
            checkpointer = checkpointer ,
        )
        
        return agent


    def get_embedding(input_text : str) -> list :
        from openai import AzureOpenAI
        AZURE_OPENAI_ENDPOINT = "https://cb-open-ai.openai.azure.com/"   ##"https://aif-ext.openai.azure.com/"
        AZURE_OPENAI_API_KEY = "3iYTlh91UL2NSnYaFIg3Me2RfWN3bg1kRbbAcuYRPJqN4hYi3J4iJQQJ99BDACYeBjFXJ3w3AAABACOG3kvE"
        AZURE_OPENAI_API_VERSION = "2025-01-01-preview"
        # import openai

        # Azure OpenAI configuration
        az_client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION
        )


        # Generate embeddings
        response = az_client.embeddings.create(
            input=input_text,
            model="text-embedding-3-small"  # This is your deployment name in Azure
        )

        embedding = response.data[0].embedding
        return(embedding)
    
    def get_schema_detail_v2(self,input_prompt: str):
        from pymilvus import MilvusClient

        mc_client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")
        COLLECTION = "schema_catalog"

        db_name = "rag_demo"

        # Create if not exists, then use
        mc_client.using_database(db_name) if db_name in mc_client.list_databases() else (mc_client.create_database(db_name) or mc_client.using_database(db_name))

        # Must load before search
        mc_client.load_collection(COLLECTION)

        query_text = "how to find the healthy score"
        query_text = "list down the patient details "
        query_text = input_prompt
        query_vec = self.get_embedding(query_text)  # your Azure embedding function
        try:
            assert len(query_vec) == 1536  # must match collection dim
        except :
            print(" dimension not matching")

        results = mc_client.search(
            collection_name=COLLECTION,
            data=[query_vec],                 # list of vectors
            anns_field="embedding",           # your vector field name
            limit=5,                          # topK
            output_fields=["full_object_name", "schema_name", "table_name", "column_name", "data_type"],
            search_params={
                "metric_type": "COSINE",
                "params": {"nprobe": 10},     # for IVF indexes; harmless to keep for many setups
            },
            # filter='schema_name == "dbo"'    # optional metadata filter (scalar filtering)
        )

        # results is List[List[dict]]: one list per query vector :contentReference[oaicite:0]{index=0}
        table_col_list ={}
        for ihit, hit in enumerate(results[0]):
            # print(hit["id"], hit["distance"], hit["entity"] ,"schema name :",hit["entity"]["full_object_name"].split('.')[0] ,
            #       "Table name :" , hit["entity"]["full_object_name"].split('.')[1] ,
            #       "column name :" , (hit["entity"]["full_object_name"].split('.')[2]).split()[0]
            #       )
            table_col_list[ihit] = {}
            table_col_list[ihit]["schema_name"] = hit["entity"]["full_object_name"].split('.')[0]
            table_col_list[ihit]["table_name"] = hit["entity"]["full_object_name"].split('.')[1]
            table_col_list[ihit]["column_name"] = (hit["entity"]["full_object_name"].split('.')[2]).split()[0]
        return table_col_list
                    
        
    def get_schema_detail(self,schema_name: str) -> dict:
        db_local = SQLDatabase.from_uri(self.DATABASE_URI, schema=schema_name)

        toolkit = SQLDatabaseToolkit(db=db_local, llm=MainClass().get_llm_client()  ) ##self._get_llm())
        tools = toolkit.get_tools()

        agent = create_agent(
            model=MainClass().get_llm_client()  , #self._get_llm(),
            tools=tools,
            system_prompt=self.system_prompt,
        )

        user_query = """List table details along with data type, primary and foreign key that I have access.
        NOTE: output in json format with schema name and tables in each schema.
        """

        response = agent.invoke({"messages": [{"role": "user", "content": user_query}]})
        text = response["messages"][-1].content

        json_str = self.extract_json_block(text)
        return json.loads(json_str)  # ✅ string -> dict

    def get_main2(self):
        # ---- main ----
        db = SQLDatabase.from_uri(self.DATABASE_URI)
        df_f = pd.DataFrame()
        query="""
        SELECT 
            cols.table_schema schema_name, 
            cols.table_name, 
            cols.column_name, 
            cols.data_type,
            -- Identify PK
            CASE WHEN pk.column_name IS NOT NULL THEN 'PK' ELSE '' END AS primary_key,
            -- Identify FK and show its target
            CASE WHEN fk.column_name IS NOT NULL THEN 'FK' ELSE '' END AS foreign_key,
            fk.referenced_table,
            fk.referenced_column,
            -- Column Comment
            pg_catalog.col_description(c.oid, cols.ordinal_position::int) AS column_description
        FROM 
            information_schema.columns cols
        JOIN 
            pg_catalog.pg_class c ON c.relname = cols.table_name
        JOIN 
            pg_catalog.pg_namespace n ON n.oid = c.relnamespace AND n.nspname = cols.table_schema
        -- Join for Primary Keys (using pg_catalog to avoid NULLs for user1)
        LEFT JOIN (
            SELECT conrelid, a.attname AS column_name
            FROM pg_catalog.pg_constraint con
            JOIN pg_catalog.pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
            WHERE con.contype = 'p'
        ) pk ON c.oid = pk.conrelid AND cols.column_name = pk.column_name
        -- Join for Foreign Keys (using pg_catalog to avoid NULLs for user1)
        LEFT JOIN (
            SELECT 
                conrelid, 
                a.attname AS column_name,
                confrelid::regclass AS referenced_table,
                af.attname AS referenced_column
            FROM pg_catalog.pg_constraint con
            JOIN pg_catalog.pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
            JOIN pg_catalog.pg_attribute af ON af.attrelid = con.confrelid AND af.attnum = ANY(con.confkey)
            WHERE con.contype = 'f'
        ) fk ON c.oid = fk.conrelid AND cols.column_name = fk.column_name
        WHERE 
            cols.table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY 
            cols.table_schema, cols.table_name, cols.ordinal_position;

        """


        rows = db._execute(query, fetch="all")
        df = pd.DataFrame(rows)

        separator ='.'
        comment_separtor ="   -   "
        df['full_object_name'] = df["schema_name"] + separator + df["table_name"] + separator + df["column_name"] + comment_separtor + np.where(df["column_description"].notnull(), df["column_description"],"")
        return df  ##.to_json()


    def get_main(self):
            system_prompt = """You are a helpful assistant for SQL database queries..."""
            db = self.get_db_conn()  ##SQLDatabase.from_uri(DATABASE_URI)

            query = """
            SELECT n.nspname AS schema_name
            FROM pg_catalog.pg_namespace n
            WHERE n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema'
            ORDER BY schema_name;
            """

            rows = db._execute(query, fetch="all")
            df = pd.DataFrame(rows)

            merged_json_data = {}

            for _, row in df.iterrows():
                schema_name = row["schema_name"]
                print("Processing schema:", schema_name)

                schema_json = self.get_schema_detail(schema_name)        # dict
                merged_json_data = merge(merged_json_data, schema_json)  # ✅ dict merge

            return(json.dumps(merged_json_data, indent=2))
