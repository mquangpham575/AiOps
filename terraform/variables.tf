variable "prefix" {
  description = "Prefix for all resources"
  default     = "aiops"
}

variable "location" {
  description = "Azure region"
  default     = "southeastasia"
}

variable "admin_username" {
  description = "Admin username for VMs"
  default     = "azureuser"
}

variable "vm_sizes" {
  description = "VM sizes for each node"
  type        = map(string)
  default = {
    control = "Standard_B2ps_v2"
    loadgen = "Standard_D2ps_v5"
    app     = "Standard_D2ps_v5"
  }
}

variable "private_ip_addresses" {
  description = "Private IP addresses for VMs"
  type        = map(string)
  default = {
    control = "10.0.1.4"
    loadgen = "10.0.1.5"
    app     = "10.0.1.6"
  }
}
