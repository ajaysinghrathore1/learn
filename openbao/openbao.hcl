ui = true
disable_mlock = true

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

api_addr = "http://localhost:8200"

storage "postgresql" {
  # connection_url can be omitted if you set BAO_PG_CONNECTION_URL
  ha_enabled = "true"
  table      = "openbao_kv_store"
  ha_table   = "openbao_ha_locks"
  max_connect_retries = 0
}
