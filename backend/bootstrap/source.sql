CREATE TABLE customers (
  customer_id BIGSERIAL PRIMARY KEY,
  full_name VARCHAR(200) NOT NULL,
  mobile_number VARCHAR(30),
  email VARCHAR(255),
  country_code CHAR(2) NOT NULL DEFAULT 'SA',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO customers(full_name, mobile_number, email) VALUES
  ('Ahmed Nassar', '+966500000001', 'ahmed@example.com'),
  ('Sara Ali', NULL, 'sara@example.com'),
  ('Omar Hassan', '050-000-0003', NULL);
