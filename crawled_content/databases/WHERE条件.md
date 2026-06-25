# WHERE条件

> 来源: https://www.runoob.com/mysql/mysql-where-clause.html
> 爬取时间: 2026-06-25 13:29:12
> 学科: databases | 难度: 基础
> 标签: 数据库, SQL, WHERE, 基础

---


# MySQL WHERE 子句


我们知道从 MySQL 表中使用SELECT语句来读取数据。


如需有条件地从表中选取数据，可将 WHERE 子句添加到 SELECT 语句中。


WHERE 子句用于在 MySQL 中过滤查询结果，只返回满足特定条件的行。


### 语法


以下是 SQL SELECT 语句使用 WHERE 子句从数据表中读取数据的通用语法：


```
SELECT column1, column2, ...
FROM table_name
WHERE condition;
```


参数说明：

**参数说明：**
- column1,column2, ... 是你要选择的列的名称，如果使用*表示选择所有列。
`column1`
`column2`
`*`
- table_name是你要从中查询数据的表的名称。
`table_name`
- WHERE condition是用于指定过滤条件的子句。
`WHERE condition`

更多说明：

**更多说明：**
- 查询语句中你可以使用一个或者多个表，表之间使用逗号,分割，并使用WHERE语句来设定查询条件。
- 你可以在 WHERE 子句中指定任何条件。
- 你可以使用 AND 或者 OR 指定一个或多个条件。
- WHERE 子句也可以运用于 SQL 的 DELETE 或者 UPDATE 命令。
- WHERE 子句类似于程序语言中的 if 条件，根据 MySQL 表中的字段值来读取指定的数据。

以下为操作符列表，可用于 WHERE 子句中。


下表中实例假定 A 为 10, B 为 20


### 简单实例


1. 等于条件：


```
SELECT * FROM users WHERE username = 'test';
```


2. 不等于条件：


```
SELECT * FROM users WHERE username != 'runoob';
```


3. 大于条件:


```
SELECT * FROM products WHERE price > 50.00;
```


4. 小于条件:


```
SELECT * FROM orders WHERE order_date < '2023-01-01';
```


5. 大于等于条件:


```
SELECT * FROM employees WHERE salary >= 50000;
```


6. 小于等于条件:


```
SELECT * FROM students WHERE age <= 21;
```


7. 组合条件（AND、OR）:


```
SELECT * FROM products WHERE category = 'Electronics' AND price > 100.00;

SELECT * FROM orders WHERE order_date >= '2023-01-01' OR total_amount > 1000.00;
```


8. 模糊匹配条件（LIKE）:


```
SELECT * FROM customers WHERE first_name LIKE 'J%';
```


9. IN 条件:


```
SELECT * FROM countries WHERE country_code IN ('US', 'CA', 'MX');
```


10. NOT 条件:


```
SELECT * FROM products WHERE NOT category = 'Clothing';
```


11. BETWEEN 条件:


```
SELECT * FROM orders WHERE order_date BETWEEN '2023-01-01' AND '2023-12-31';
```


12. IS NULL 条件


```
SELECT * FROM employees WHERE department IS NULL;
```


13. IS NOT NULL 条件:


```
SELECT * FROM customers WHERE email IS NOT NULL;
```


如果我们想在 MySQL 数据表中读取指定的数据，WHERE 子句是非常有用的。


使用主键来作为 WHERE 子句的条件查询是非常快速的。


如果给定的条件在表中没有任何匹配的记录，那么查询不会返回任何数据。


## 从命令提示符中读取数据


我们将在SELECT语句使用 WHERE 子句来读取 MySQL 数据表 runoob_tbl 中的数据。


以下实例将读取 runoob_tbl 表中 runoob_author 字段值为 Sanjay 的所有记录：


## SQL SELECT WHERE 子句


输出结果：


MySQL 的 WHERE 子句的字符串比较是不区分大小写的。
你可以使用 BINARY 关键字来设定 WHERE 子句的字符串比较是区分大小写的。


如下实例:


## BINARY 关键字


实例中使用了BINARY关键字，是区分大小写的，所以runoob_author='runoob.com'的查询条件是没有数据的。

**BINARY**
**runoob_author='runoob.com'**

## 使用 PHP 脚本读取数据


你可以使用 PHP 函数的 mysqli_query() 及相同的 SQL SELECT 带上 WHERE 子句的命令来获取数据。


该函数用于执行 SQL 命令，然后通过 PHP 函数 mysqli_fetch_array() 来输出所有查询的数据。


### 实例


以下实例将从 runoob_tbl 表中返回使用 runoob_author 字段值为RUNOOB.COM的记录：


## MySQL WHERE 子句测试：


输出结果如下所示：

