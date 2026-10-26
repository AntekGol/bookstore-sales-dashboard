SELECT
    strftime(date, '%Y-%m-%d') AS day,
    ROUND(SUM(paid_price), 2) AS revenue
FROM orders
GROUP BY date
ORDER BY revenue DESC
LIMIT 5;
