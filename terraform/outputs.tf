# =============================================================================
# outputs.tf — Public IP and connection examples
# =============================================================================

output "public_ip" {
  description = "The public IP address of the AiOps Azure VM"
  value       = azurerm_public_ip.app.ip_address
}

output "ssh_command" {
  description = "Command to connect to the VM via SSH"
  value       = "ssh -i ~/.ssh/aiops_key azureuser@${azurerm_public_ip.app.ip_address}"
}

output "docker_host_command" {
  description = "Example command to test remote Docker connectivity"
  value       = "docker -H tcp://${azurerm_public_ip.app.ip_address}:2375 ps"
}
