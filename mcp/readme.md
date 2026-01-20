### MCP server for sql database using FASTMCP

features:
1. Add rows
2. Describe table
3. draw ERD using the given table as center point and depth level

### MCP Server 
1. Connect given database using config file and response the output
2. List of Tool and Prompt used by client

### MCP Client
1. Connect the LLM
2. Use SQLDatabaseToolkit tool to connect the database and generate the Query
3. call the appropriate tool
4. Send the response to front end
