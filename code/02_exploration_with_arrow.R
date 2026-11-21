library(arrow)
library(tidyverse)
library(scales)
theme_set(theme_minimal())

trips <- open_dataset("data/parquet_files", format = "parquet")

# Total amount charged to passengers by year and month
monthly_amounts <- trips |>
  summarize(amount = sum(total_amount), .by = c(pickup_year, pickup_month)) |>
  collect()

p <- ggplot(
  monthly_amounts,
  aes(pickup_month, amount, color = as.character(pickup_year))
) +
  geom_line() +
  scale_x_continuous(breaks = 1:12) +
  scale_y_continuous(labels = label_dollar(scale_cut = cut_short_scale())) +
  labs(color = "Year", y = "Monthly Total Amount Charged")

ggsave("outputs/01_monthly_amts.jpg", p, width = 6, height = 4, units = "in")

# Distance covered in a month per year
monthly_dist <- trips |>
  summarize(dist = sum(trip_distance), .by = c(pickup_year, pickup_month)) |>
  collect()

ggplot(
  monthly_dist,
  aes(pickup_month, dist, color = as.character(pickup_year))
) +
  geom_line() +
  scale_x_continuous(breaks = 1:12) +
  labs(color = "Year", y = "Trip Distance (Miles)")
