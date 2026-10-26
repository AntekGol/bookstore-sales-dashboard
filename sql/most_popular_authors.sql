WITH sold_per_author_set AS (
    SELECT
        books.author_set,
        SUM(orders.quantity) AS books_sold
    FROM orders
    JOIN books ON books.id = orders.book_id
    GROUP BY books.author_set
)
SELECT
    author_set,
    books_sold
FROM sold_per_author_set
WHERE books_sold = (SELECT MAX(books_sold) FROM sold_per_author_set)
ORDER BY author_set;
