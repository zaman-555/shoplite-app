CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products (id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

INSERT INTO products (name, price, stock)
VALUES
    ('Wireless Mouse', 24.99, 100),
    ('Mechanical Keyboard', 89.99, 50),
    ('USB-C Hub', 39.50, 75),
    ('Laptop Stand', 29.00, 60),
    ('Noise-Cancelling Headphones', 129.99, 40),
    ('Webcam 1080p', 49.99, 80),
    ('27-inch Monitor', 249.00, 25),
    ('Desk Lamp', 19.99, 120),
    ('Portable SSD 1TB', 99.00, 45),
    ('Ethernet Cable', 12.50, 200),
    ('Notebook', 4.99, 300),
    ('Water Bottle', 14.00, 150)
ON CONFLICT (name) DO NOTHING;
