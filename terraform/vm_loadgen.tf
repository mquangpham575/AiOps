resource "azurerm_network_interface" "loadgen" {
  name                = "${var.prefix}-loadgen-nic"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "static"
    private_ip_address            = var.private_ip_addresses["loadgen"]
  }
}

resource "azurerm_linux_virtual_machine" "loadgen" {
  name                            = "${var.prefix}-loadgen"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  size                            = var.vm_sizes["loadgen"]
  admin_username                  = var.admin_username
  disable_password_authentication = true

  network_interface_ids = [azurerm_network_interface.loadgen.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = file("${path.module}/../.ssh/aiops3_key_rsa.pub")
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  tags = {
    role        = "loadgen"
    environment = "production"
  }
}
