provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "apis" {
  for_each = toset([
    "pubsub.googleapis.com",
    "chat.googleapis.com",
  ])

  service            = each.key
  disable_on_destroy = false
}

resource "google_pubsub_topic" "gchat_events" {
  name       = var.topic_name
  depends_on = [google_project_service.apis]
}

# Allow Google Chat backend to push messages into our Pub/Sub topic
resource "google_pubsub_topic_iam_member" "gchat_push_publisher" {
  topic  = google_pubsub_topic.gchat_events.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:chat-api-push@system.gserviceaccount.com"
}

resource "google_pubsub_subscription" "gchat_pull_sub" {
  name  = var.subscription_name
  topic = google_pubsub_topic.gchat_events.id

  ack_deadline_seconds       = 30
  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "gateway_bot" {
  account_id   = var.service_account_id
  display_name = "Support Gateway Bot"
}

resource "google_pubsub_subscription_iam_member" "gateway_subscriber" {
  subscription = google_pubsub_subscription.gchat_pull_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.gateway_bot.email}"
}
