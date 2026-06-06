variable "aws_region" {
  description = "AWS 部署區域"
  type        = string
  default     = "ap-northeast-1"
}

variable "scraper_image_tag" {
  description = "Scraper Lambda 容器映像的 tag（由 deploy.sh 動態帶入，預設 latest 方便首次 plan）"
  type        = string
  default     = "latest"
}

variable "scraper_schedule_expression" {
  description = "EventBridge Scheduler 排程，預設每 4 小時"
  type        = string
  default     = "rate(4 hours)"
}

variable "scraper_max_pages" {
  description = "Scraper Lambda 每次最多爬幾頁（每頁 30 筆）"
  type        = number
  default     = 5
}

variable "listing_ttl_days" {
  description = "物件消失後幾天從 DB 刪除（持續在架者每次掃描刷新，不會被刪）"
  type        = number
  default     = 7
}

variable "fresh_window_days" {
  description = "/list 只顯示最近幾天內仍確認在架的物件"
  type        = number
  default     = 3
}
