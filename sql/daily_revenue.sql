SELECT
    date,
    ROUND(SUM(paid_price), 2) AS revenue
FROM orders
GROUP BY date
ORDER BY date;
