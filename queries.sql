-- Get user_stock_depot data --
SELECT symbol, value FROM user_stock_depot
JOIN users ON user_stock_depot.user_id = users.id
JOIN stock_symbols ON user_stock_depot.symbol_id = stock_symbols.id
WHERE users.id = ?;

-- Get transaction data --
SELECT * FROM transactions
JOIN stock_symbols ON transactions.symbol_id = stock_symbols.id
JOIN transaction_type ON transactions.transaction_type = transaction_type.id
WHERE user_id = ?;

-- Get shares --
SELECT value FROM user_stock_depot
JOIN stock_symbols ON user_stock_depot.symbol_id = stock_symbols.id
WHERE user_id = ? AND symbol = ?;