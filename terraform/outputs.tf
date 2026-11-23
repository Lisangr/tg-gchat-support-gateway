output "pubsub_topic_id" {
  description = "Full Pub/Sub topic resource name for Google Chat API Configuration"
  value       = google_pubsub_topic.gchat_events.id
}

output "pubsub_subscription_id" {
  description = "Full Pub/Sub subscription name for PUBSUB_SUBSCRIPTION env var"
  value       = google_pubsub_subscription.gchat_pull_sub.id
}

output "service_account_email" {
  description = "Service account email to generate JSON key for the gateway"
  value       = google_service_account.gateway_bot.email
}
