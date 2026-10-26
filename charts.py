import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


def save_daily_revenue_chart(daily_revenue, store_name, output_path):
    dates = pd.to_datetime([row["date"] for row in daily_revenue])
    revenue = [row["revenue"] for row in daily_revenue]

    figure, axis = plt.subplots(figsize=(12, 5))
    axis.plot(dates, revenue, color="#206bc4", linewidth=1.2)
    axis.set_title(f"{store_name} daily revenue")
    axis.set_xlabel("Date")
    axis.set_ylabel("Revenue (USD)")
    axis.grid(alpha=0.3)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    figure.autofmt_xdate()
    figure.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=120)
    plt.close(figure)
