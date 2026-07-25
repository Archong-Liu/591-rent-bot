variable "aws_region" {
  description = "AWS deployment region"
  type        = string
  default     = "ap-northeast-1"
}

variable "scraper_image_tag" {
  description = "Scraper Lambda container image tag (passed dynamically by deploy.sh; defaults to latest so the first plan works)"
  type        = string
  default     = "latest"
}

variable "scraper_schedule_expression" {
  description = "EventBridge Scheduler schedule; defaults to once a day at noon (Asia/Taipei, set via schedule_expression_timezone in eventbridge.tf)"
  type        = string
  default     = "cron(0 12 * * ? *)"
}

variable "scraper_max_pages" {
  description = "Max pages the Scraper Lambda fetches per run (30 listings/page)"
  type        = number
  default     = 5
}

variable "listing_ttl_days" {
  description = "Days after a listing disappears before it's deleted from the table (listings still live get their TTL refreshed on every scan, so they're never deleted)"
  type        = number
  default     = 7
}

variable "fresh_window_days" {
  description = "/list only shows listings confirmed live within this many days. With a once-daily scan, 2 tolerates exactly one missed/failed scan (e.g. an anti-bot 419) before a still-live listing would be treated as stale"
  type        = number
  default     = 2
}
