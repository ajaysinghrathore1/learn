from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase


class database_client():
    def __init__(self, userId ="user1", password="user1", host="localhost", port="5432", database = "postgres"):
        self.userId = userId
        self.password = password
        self.host = host
        self.port = port
        self.database = database

    def get_postgres_connection_string(self):
        DATABASE_URI = f"postgresql+psycopg2://{self.userId}:{self.password}@{self.host}:{self.port}/{self.database}"
        return DATABASE_URI

    def get_db_client(self):
        DB_URI = self.get_postgres_connection_string()
        engine = create_engine(DB_URI)
        db = SQLDatabase(engine)
        return db
    
