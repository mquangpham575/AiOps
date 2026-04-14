# =============================================================================
# nsg.tf — Network Security Group for AiOps Application Plane (per-NIC)
# =============================================================================

resource "azurerm_network_security_group" "app" {
  name                = "${var.project_name}-app-nsg"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  # ---- SSH (port 22) — also carries Docker tunnel ----
  security_rule {
    name                       = "allow-ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  # ---- HTTP (port 80) — Target App ----
  security_rule {
    name                       = "allow-http-app"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # ---- Node Exporter (port 9100) ----
  security_rule {
    name                       = "allow-node-exporter"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "9100"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  # ---- cAdvisor (port 8080) ----
  security_rule {
    name                       = "allow-cadvisor"
    priority                   = 140
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8080"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  tags = {
    project = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Associate the NSG with the app VM NIC (not the subnet)
# ---------------------------------------------------------------------------
resource "azurerm_network_interface_security_group_association" "app" {
  network_interface_id      = azurerm_network_interface.app.id
  network_security_group_id = azurerm_network_security_group.app.id
}
