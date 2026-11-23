variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "Default GCP region"
  type        = string
  default     = "europe-central2"
}

variable "topic_name" {
  description = "Pub/Sub topic name for Google Chat incoming events"
  type        = string
  default     = "support-gateway-events"
}

variable "subscription_name" {
  description = "Pub/Sub pull subscription name"
  type        = string
  default     = "support-gateway-sub"
}

variable "service_account_id" {
  description = "Service account ID for the support gateway bot"
  type        = string
  default     = "support-gateway-bot"
}
