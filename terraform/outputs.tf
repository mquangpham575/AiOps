output "resource_group" {
  description = "Resource group name"
  value       = azurerm_resource_group.main.name
}

output "vnet" {
  description = "Virtual network name"
  value       = azurerm_virtual_network.main.name
}

output "subnet" {
  description = "Subnet name"
  value       = azurerm_subnet.main.name
}

output "vm_ips" {
  description = "Private IP addresses of all VMs"
  value = {
    control = azurerm_linux_virtual_machine.control.private_ip_address
    loadgen = azurerm_linux_virtual_machine.loadgen.private_ip_address
    app     = azurerm_linux_virtual_machine.app.private_ip_address
  }
}

output "vm_public_ips" {
  description = "Public IP addresses of all VMs"
  value = {
    control = azurerm_network_interface.control.ip_configuration[0].public_ip_address_id != null ? azurerm_linux_virtual_machine.control.public_ip_address : "N/A"
    loadgen = azurerm_linux_virtual_machine.loadgen.public_ip_address
    app     = azurerm_linux_virtual_machine.app.public_ip_address
  }
}

output "ssh_connection" {
  description = "SSH connection commands"
  value = {
    control = "ssh -i ./.ssh/aiops3_key ${var.admin_username}@<control-public-ip>"
    loadgen = "ssh -i ./.ssh/aiops3_key ${var.admin_username}@<loadgen-public-ip>"
    app     = "ssh -i ./.ssh/aiops3_key ${var.admin_username}@<app-public-ip>"
  }
}
