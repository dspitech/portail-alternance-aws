variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "suffix" {
  description = "Suffixe unique (évite les collisions de noms de bucket, globalement uniques sur AWS)"
  type        = string
}
