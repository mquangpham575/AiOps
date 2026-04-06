# =============================================================================
# vms.tf — Public IP, NIC, and Linux VM for AiOps Application Plane
# =============================================================================

# ---------------------------------------------------------------------------
# cloud-init script — Installs Docker and enables TCP access on port 2375
# ---------------------------------------------------------------------------
locals {
  cloud_init_script = base64encode(<<-CLOUDINIT
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
      # ---- Docker Installation (Official Ubuntu apt) ----
      - mkdir -p /etc/apt/keyrings
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
      - apt-get update -qq
      - apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
      
      # ---- Enable Docker TCP API (Port 2375) ----
      # This is based on Section 6.1.3 of docs/infra_new.md
      - mkdir -p /etc/systemd/system/docker.service.d
      - |
        cat <<EOF > /etc/systemd/system/docker.service.d/override.conf
        [Service]
        ExecStart=
        ExecStart=/usr/bin/dockerd
        EOF
      - |
        cat <<EOF > /etc/docker/daemon.json
        {
          "hosts": ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2375"]
        }
        EOF
        
      # ---- Apply changes ----
      - systemctl daemon-reload
      - systemctl restart docker
      
      # ---- Add default 'azureuser' to docker group ----
      - usermod -aG docker azureuser

    final_message: "AiOps Application Plane ready after $UPTIME seconds"
  CLOUDINIT
  )
}

# ---------------------------------------------------------------------------
# Public IP
# ---------------------------------------------------------------------------
resource "azurerm_public_ip" "app" {
  name                = "${var.project_name}-pip"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    project = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Network Interface
# ---------------------------------------------------------------------------
resource "azurerm_network_interface" "app" {
  name                = "${var.project_name}-nic"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.app.id
  }

  tags = {
    project = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Linux Virtual Machine (ARM64)
# ---------------------------------------------------------------------------
resource "azurerm_linux_virtual_machine" "app" {
  name                = "${var.project_name}-vm"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.vm_size

  admin_username                  = "azureuser"
  disable_password_authentication = true

  admin_ssh_key {
    username   = "azureuser"
    public_key = file(var.ssh_public_key_path)
  }

  network_interface_ids = [azurerm_network_interface.app.id]

  os_disk {
    name                 = "${var.project_name}-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-arm64"
    version   = "latest"
  }

  custom_data = local.cloud_init_script

  tags = {
    project = var.project_name
    role    = "application-plane"
  }
}
