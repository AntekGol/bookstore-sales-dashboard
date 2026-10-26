WITH spending_per_customer AS (
    SELECT
        users.customer_id,
        ROUND(SUM(orders.paid_price), 2) AS total_spent
    FROM orders
    JOIN users ON users.id = orders.user_id
    GROUP BY users.customer_id
),
best_customer AS (
    SELECT customer_id, total_spent
    FROM spending_per_customer
    ORDER BY total_spent DESC
    LIMIT 1
)
SELECT
    best_customer.customer_id,
    best_customer.total_spent,
    LIST(users.id ORDER BY users.id) AS user_ids
FROM best_customer
JOIN users ON users.customer_id = best_customer.customer_id
GROUP BY best_customer.customer_id, best_customer.total_spent;
