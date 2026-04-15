resource "azurerm_network_security_group" "control" {
  name                = "${var.prefix}-control-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                   = "SSH"
    priority               = 100
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "22"
    source_address_prefix  = "*"
    description            = "SSH access"
  }

  security_rule {
    name                   = "HTTP"
    priority               = 110
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "80"
    source_address_prefix  = "*"
    description            = "HTTP access"
  }

  security_rule {
    name                   = "Prometheus"
    priority               = 120
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "9090"
    source_address_prefix  = "10.0.1.0/24"
    description            = "Prometheus scrape from VNet"
  }

  security_rule {
    name                   = "Grafana"
    priority               = 130
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "3000"
    source_address_prefix  = "*"
    description            = "Grafana UI"
  }

  tags = {
    role = "control"
  }
}

resource "azurerm_network_security_group" "loadgen" {
  name                = "${var.prefix}-loadgen-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                   = "SSH"
    priority               = 100
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "22"
    source_address_prefix  = "*"
    description            = "SSH access"
  }

  security_rule {
    name                   = "HTTP"
    priority               = 110
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "80"
    source_address_prefix  = "10.0.1.0/24"
    description            = "HTTP from VNet"
  }

  security_rule {
    name                   = "NodeExporter"
    priority               = 120
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "9100"
    source_address_prefix  = "10.0.1.0/24"
    description            = "Node exporter from VNet"
  }

  tags = {
    role = "loadgen"
  }
}

resource "azurerm_network_security_group" "app" {
  name                = "${var.prefix}-app-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                   = "SSH"
    priority               = 100
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "22"
    source_address_prefix  = "*"
    description            = "SSH access"
  }

  security_rule {
    name                   = "HTTP"
    priority               = 110
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "80"
    source_address_prefix  = "10.0.1.0/24"
    description            = "HTTP from VNet"
  }

  security_rule {
    name                   = "NodeExporter"
    priority               = 120
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "9100"
    source_address_prefix  = "10.0.1.0/24"
    description            = "Node exporter from VNet"
  }

  security_rule {
    name                   = "Cadvisor"
    priority               = 130
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "8080"
    source_address_prefix  = "10.0.1.0/24"
    description            = "cAdvisor from VNet"
  }

  tags = {
    role = "app"
  }
}

resource "azurerm_network_interface_security_group_association" "control" {
  network_interface_id      = azurerm_network_interface.control.id
  network_security_group_id = azurerm_network_security_group.control.id
}

resource "azurerm_network_interface_security_group_association" "loadgen" {
  network_interface_id      = azurerm_network_interface.loadgen.id
  network_security_group_id = azurerm_network_security_group.loadgen.id
}

resource "azurerm_network_interface_security_group_association" "app" {
  network_interface_id      = azurerm_network_interface.app.id
  network_security_group_id = azurerm_network_security_group.app.id
}
