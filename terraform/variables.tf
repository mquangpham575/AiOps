# =============================================================================
# variables.tf — Input variables for AiOps Azure infrastructure
# =============================================================================

variable "project_name" {
  description = "Project name used as a prefix for all resource names"
  type        = string
  default     = "aiops"
}

variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
  default     = "rg-aiops"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "Southeast Asia"
}

variable "vm_size" {
  description = "Azure VM SKU (ARM64 recommended for student accounts)"
  type        = string
  default     = "Standard_B2ps_v2"
}

variable "ssh_public_key_path" {
  description = "Absolute path to the SSH public key file (.pub)"
  type        = string
  default     = "~/.ssh/aiops_key.pub"
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to reach port 22 and 2375."
  type        = string
  default     = "14.187.86.16/32"
}
