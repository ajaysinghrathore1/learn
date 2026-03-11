# from openai import AzureOpenAI
import os
import psycopg2
from langchain_community.utilities import SQLDatabase
from langchain_openai.chat_models.azure import AzureChatOpenAI

import datetime
import uuid
import secrets
# ---------- Azure OpenAI client ----------
# Initialize AzureChatOpenAI
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

class MainClass():
    def __init__(self):
        self.AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
        self.AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
        self.AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    
    def get_llm_client(self):
        if not (self.AZURE_OPENAI_ENDPOINT and self.AZURE_OPENAI_API_KEY and self.AZURE_OPENAI_DEPLOYMENT):
            raise RuntimeError(
                "Please set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, "
                "and AZURE_OPENAI_DEPLOYMENT environment variables."
            )

        # self.client = AzureOpenAI(
        #     azure_endpoint=self.AZURE_OPENAI_ENDPOINT,
        #     api_key=self.AZURE_OPENAI_API_KEY,
        #     api_version=self.AZURE_OPENAI_API_VERSION,
        # )

        self.client = AzureChatOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            openai_api_version=AZURE_OPENAI_API_VERSION,
            deployment_name=AZURE_OPENAI_DEPLOYMENT,
            openai_api_key=AZURE_OPENAI_API_KEY,
            openai_api_type="azure",
            temperature=0.0,
            timeout=60.0,
            max_retries=2,
        )

        return self.client
    
    def get_postgres_db_client(self, userId, password, host, port, database):
        connection = psycopg2.connect(
            host=host,          # Database server address (e.g., "localhost" or an IP)
            database=database,    # Name of the database
            user=userId,      # Your PostgreSQL username
            password=password,  # Your PostgreSQL password
            port=port                # Port number (default is 5432)
        )

        return connection
    
    def get_postgres_connection_string(self, userId, password, host, port, database):
        DATABASE_URI = f"postgresql+psycopg2://{userId}:{password}@{host}:{port}/{database}"
        # Create an instance of SQLDatabase
        try:
            db = SQLDatabase.from_uri(DATABASE_URI)
            print("Successfully connected to the PostgreSQL database with LangChain's SQLDatabase.")
            
            # Optional: Print some database info to verify
            # print(db.get_usable_table_names())

        except Exception as e:
            print(f"Error connecting to the database: {e}")
        return db    
    
    def generate_unique_key(self, num_random_strings=5):
        """
        Generates a unique key based on the current date and time
        and a specified number of unique random strings.
        """
        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y%m%d%H%M%S%f")
        unique_strings = []
        generated_set = set()
        for _ in range(num_random_strings):
            random_part = secrets.token_hex(4)
            while random_part in generated_set:
                random_part = secrets.token_hex(4)
            generated_set.add(random_part)
            unique_strings.append(random_part)
        key = f"{timestamp_str}_{'_'.join(unique_strings)}"
        return key    
