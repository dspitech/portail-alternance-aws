variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "suffix" {
  type = string
}

variable "allowed_origin" {
  description = "Origine CORS autorisée (URL CloudFront du dashboard)"
  type        = string
}
