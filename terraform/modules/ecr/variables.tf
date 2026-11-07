variable "name" {
  description = "Name prefix."
  type        = string
}

variable "repositories" {
  description = "Image names to create. Each becomes <name>/<repository>."
  type        = list(string)
}
