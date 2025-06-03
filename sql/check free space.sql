SELECT DB_NAME(database_id) AS database_name, 
    type_desc, 
    name AS FileName, 
    size/128.0 AS CurrentSizeMB
FROM sys.master_files
WHERE 
DB_NAME(database_id)='SSISDB'
--database_id > 6 AND type IN (0,1)


SELECT DB_NAME() AS DbName, 
    name AS FileName, 
    type_desc,
    cast((size/128.0)/1000  as numeric(15,2)) AS CurrentSizeGB,  
    cast((size/128.0)/1000 - (CAST(FILEPROPERTY(name, 'SpaceUsed') AS INT)/128.0)/1000  as numeric(15,2)) AS FreeSpaceGB
FROM sys.database_files
WHERE 
DB_NAME()='SSISDB'

SELECT name, log_reuse_wait_desc, recovery_model, recovery_model_desc FROM sys.databases;
