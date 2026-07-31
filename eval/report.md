# Text-to-SQL Evaluation Report
**Date:** 2026-07-30 20:04:36
**Model:** llama-3.3-70b-versatile

## Summary Metrics
- **Overall Accuracy:** 60.0% (12/20)
- **Average Latency:** 1922 ms
- **Average Retries:** 0.00

## Accuracy by Difficulty
- **Easy:** 85.7% (6/7)
- **Medium:** 62.5% (5/8)
- **Hard:** 20.0% (1/5)

## Detailed Results

| ID   | Difficulty   | Status   | Latency   |   Retries | Failure Reason                    |
|:-----|:-------------|:---------|:----------|----------:|:----------------------------------|
| Q01  | easy         | ✅ Pass  | 1035ms    |         0 | -                                 |
| Q02  | easy         | ✅ Pass  | 1544ms    |         0 | -                                 |
| Q03  | medium       | ❌ Fail  | 1234ms    |         0 | Missing expected table: Customers |
| Q04  | medium       | ✅ Pass  | 1767ms    |         0 | -                                 |
| Q05  | easy         | ❌ Fail  | 945ms     |         0 | Data check failed: Value 0 < 100  |
| Q06  | easy         | ✅ Pass  | 945ms     |         0 | -                                 |
| Q07  | medium       | ✅ Pass  | 1457ms    |         0 | -                                 |
| Q08  | easy         | ✅ Pass  | 740ms     |         0 | -                                 |
| Q09  | hard         | ❌ Fail  | 591ms     |         0 | Expected 10-12 rows, got 0        |
| Q10  | hard         | ✅ Pass  | 1504ms    |         0 | -                                 |
| Q11  | medium       | ✅ Pass  | 843ms     |         0 | -                                 |
| Q12  | hard         | ❌ Fail  | 1047ms    |         0 | Expected 10-100 rows, got 1       |
| Q13  | medium       | ✅ Pass  | 1373ms    |         0 | -                                 |
| Q14  | easy         | ✅ Pass  | 1234ms    |         0 | -                                 |
| Q15  | medium       | ❌ Fail  | 945ms     |         0 | Expected 1-50 rows, got 93        |
| Q16  | medium       | ✅ Pass  | 3183ms    |         0 | -                                 |
| Q17  | hard         | ❌ Fail  | 2505ms    |         0 | Expected 2-4 rows, got 0          |
| Q18  | medium       | ❌ Fail  | 5032ms    |         0 | Missing expected table: Employees |
| Q19  | easy         | ✅ Pass  | 4808ms    |         0 | -                                 |
| Q20  | hard         | ❌ Fail  | 5716ms    |         0 | Expected 2-5 rows, got 12         |

## Failed Queries Analysis

### Q03: Which country had the most orders?
**Reason:** Missing expected table: Customers
**Generated SQL:**
```sql
SELECT ShipCountry, COUNT(OrderID) AS OrderCount FROM Orders GROUP BY ShipCountry ORDER BY OrderCount DESC LIMIT 100
```

### Q05: How many orders were placed in 1997?
**Reason:** Data check failed: Value 0 < 100
**Generated SQL:**
```sql
SELECT COUNT(*) AS OrderCount FROM Orders WHERE strftime('%Y', OrderDate) = '1997' LIMIT 100
```

### Q09: What are the monthly sales totals for 1997?
**Reason:** Expected 10-12 rows, got 0
**Generated SQL:**
```sql
SELECT strftime('%Y-%m', o.OrderDate) AS Month, ROUND(SUM(od.UnitPrice * od.Quantity * (1 - od.Discount)), 2) AS SalesTotal FROM Orders o JOIN "Order Details" od ON o.OrderID = od.OrderID WHERE strftime('%Y', o.OrderDate) = '1997' GROUP BY Month ORDER BY Month LIMIT 100
```

### Q12: What is the average order value per customer?
**Reason:** Expected 10-100 rows, got 1
**Generated SQL:**
```sql
SELECT AVG(TotalValue) FROM (SELECT c.CustomerID, ROUND(SUM(od.UnitPrice * od.Quantity), 2) AS TotalValue FROM Customers c JOIN Orders o ON c.CustomerID = o.CustomerID JOIN "Order Details" od ON o.OrderID = od.OrderID GROUP BY c.CustomerID) LIMIT 100
```

### Q15: Which customers have placed more than 10 orders?
**Reason:** Expected 1-50 rows, got 93
**Generated SQL:**
```sql
SELECT c.CustomerID, c.CompanyName, COUNT(o.OrderID) AS OrderCount FROM Customers c JOIN Orders o ON c.CustomerID = o.CustomerID GROUP BY c.CustomerID, c.CompanyName HAVING COUNT(o.OrderID) > 10 ORDER BY OrderCount DESC LIMIT 100
```

### Q17: Show the order count by quarter for 1996
**Reason:** Expected 2-4 rows, got 0
**Generated SQL:**
```sql
SELECT CAST(strftime('%m', o.OrderDate) AS INTEGER) / 3 + 1 AS Quarter, COUNT(o.OrderID) AS OrderCount FROM Orders o WHERE strftime('%Y', o.OrderDate) = '1996' GROUP BY Quarter ORDER BY Quarter LIMIT 10000
```

### Q18: Which region has the most employees?
**Reason:** Missing expected table: Employees
**Generated SQL:**
```sql
SELECT r.RegionDescription, COUNT(DISTINCT et.EmployeeID) AS EmployeeCount FROM Regions r JOIN EmployeeTerritories et ON r.RegionID = (SELECT RegionID FROM Territories WHERE TerritoryID = et.TerritoryID) GROUP BY r.RegionID, r.RegionDescription ORDER BY EmployeeCount DESC LIMIT 100
```

### Q20: Show the total revenue per year across all orders
**Reason:** Expected 2-5 rows, got 12
**Generated SQL:**
```sql
SELECT strftime('%Y', o.OrderDate) AS Year, ROUND(SUM(od.UnitPrice * od.Quantity * (1 - od.Discount)), 2) AS TotalRevenue FROM Orders o JOIN "Order Details" od ON o.OrderID = od.OrderID GROUP BY Year ORDER BY Year LIMIT 100
```
