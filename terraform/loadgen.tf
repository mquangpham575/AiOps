# =============================================================================
# loadgen.tf — Load Generator + Observability VM (2nd VM)
# =============================================================================

locals {
  loadgen_cloud_init_script = base64encode(<<-CLOUDINIT
    #cloud-config
    package_update: true
    package_upgrade: false

    packages:
      - apt-transport-https
      - ca-certificates
      - curl
      - gnupg
      - lsb-release

    runcmd:
      - mkdir -p /etc/apt/keyrings
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
      - apt-get update -qq
      - apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
      - usermod -aG docker azureuser

    final_message: "AiOps Loadgen Plane ready after $UPTIME seconds"
  CLOUDINIT
  )
}

resource "azurerm_public_ip" "loadgen" {
  name                = "${var.project_name}-loadgen-pip"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    project = var.project_name
    role    = "loadgen-observability"
  }
}

resource "azurerm_network_interface" "loadgen" {
  name                = "${var.project_name}-loadgen-nic"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.loadgen.id
  }

  tags = {
    project = var.project_name
    role    = "loadgen-observability"
  }
}

resource "azurerm_network_security_group" "loadgen" {
  name                = "${var.project_name}-loadgen-nsg"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

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

  security_rule {
    name                       = "allow-otel-grpc"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "4317"
    source_address_prefix      = "10.0.0.0/16"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-grafana"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3000"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-prometheus"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "9090"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-jaeger"
    priority                   = 140
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "16686"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-node-exporter"
    priority                   = 150
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "9100"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  tags = {
    project = var.project_name
    role    = "loadgen-observability"
  }
}

resource "azurerm_network_interface_security_group_association" "loadgen" {
  network_interface_id      = azurerm_network_interface.loadgen.id
  network_security_group_id = azurerm_network_security_group.loadgen.id
}

resource "azurerm_linux_virtual_machine" "loadgen" {
  name                = "${var.project_name}-loadgen-vm"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.loadgen_vm_size

  admin_username                  = "azureuser"
  disable_password_authentication = true

  admin_ssh_key {
    username   = "azureuser"
    public_key = file(var.ssh_public_key_path)
  }

  network_interface_ids = [azurerm_network_interface.loadgen.id]

  os_disk {
    name                 = "${var.project_name}-loadgen-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  custom_data = local.loadgen_cloud_init_script

  tags = {
    project = var.project_name
    role    = "loadgen-observability"
  }
}
