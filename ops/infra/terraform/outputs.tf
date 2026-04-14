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

output "docker_tunnel_command" {
  description = "SSH tunnel for remote Docker access (run before starting agents)"
  value       = "ssh -i ~/.ssh/aiops_key -N -L 2375:/var/run/docker.sock azureuser@${azurerm_public_ip.app.ip_address}"
}

output "loadgen_public_ip" {
  description = "The public IP address of the AiOps loadgen VM"
  value       = azurerm_public_ip.loadgen.ip_address
}

output "loadgen_ssh_command" {
  description = "Command to connect to the loadgen VM via SSH"
  value       = "ssh -i ~/.ssh/aiops_key azureuser@${azurerm_public_ip.loadgen.ip_address}"
}
