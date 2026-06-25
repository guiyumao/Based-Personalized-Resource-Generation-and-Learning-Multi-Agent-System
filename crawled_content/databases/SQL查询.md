# SQL查询

> 来源: https://www.runoob.com/mysql/mysql-select-query.html
> 爬取时间: 2026-06-25 13:29:10
> 学科: databases | 难度: 基础
> 标签: 数据库, SQL, SELECT, 基础

---


# MySQL 查询数据


MySQL 数据库使用SELECT语句来查询数据。


你可以通过mysql>命令提示窗口中在数据库中查询数据，或者通过 PHP 脚本来查询数据。


### 语法


以下为在 MySQL 数据库中查询数据通用的 SELECT 语法：


```
SELECT column1, column2, ...
FROM table_name
[WHERE condition]
[ORDER BY column_name [ASC | DESC]]
[LIMIT number];
```


参数说明：

**参数说明：**
- column1,column2, ... 是你想要选择的列的名称，如果使用*表示选择所有列。
`column1`
`column2`
`*`
- table_name是你要从中查询数据的表的名称。
`table_name`
- WHERE condition是一个可选的子句，用于指定过滤条件，只返回符合条件的行。
`WHERE condition`
- ORDER BY column_name [ASC | DESC]是一个可选的子句，用于指定结果集的排序顺序，默认是升序（ASC）。
`ORDER BY column_name [ASC | DESC]`
- LIMIT number是一个可选的子句，用于限制返回的行数。
`LIMIT number`

MySQL SELECT 语句简单的应用实例：


## 实例


SELECT 语句可以是灵活的，我们可以根据实际需求组合和使用这些子句，比如同时使用 WHERE 和 ORDER BY 子句，或者使用 LIMIT 控制返回的行数。


在WHERE子句中，你可以使用各种条件运算符（如=,<,>,<=,>=,!=），逻辑运算符（如AND,OR,NOT），以及通配符（如%）等。

`WHERE`
`=`
`<`
`>`
`<=`
`>=`
`!=`
`AND`
`OR`
`NOT`
`%`

以下是一些进阶的 SELECT 语句实例：


## 通过命令提示符获取数据


以下实例我们将通过 SQL SELECT 命令来获取 MySQL 数据表 runoob_tbl 的数据：


### 实例


以下实例将返回数据表 runoob_tbl 的所有记录:


## 读取数据表：


输出结果：


## 使用 PHP 脚本来获取数据


使用 PHP 函数的mysqli_query()及SQL SELECT命令来获取数据。


该函数用于执行 SQL 命令，然后通过 PHP 函数mysqli_fetch_array()来使用或输出所有查询的数据。


mysqli_fetch_array()函数从结果集中取得一行作为关联数组，或数字数组，或二者兼有
返回根据从结果集取得的行生成的数组，如果没有更多行则返回 false。


以下实例为从数据表 runoob_tbl 中读取所有记录。


尝试以下实例来显示数据表 runoob_tbl 的所有记录。使用 mysqli_fetch_array MYSQLI_ASSOC 参数获取数据：<?php$dbhost='localhost';//mysql服务器主机地址$dbuser='root';//mysql用户名$dbpass='123456';//mysql用户名密码$conn=mysqli_connect($dbhost,$dbuser,$dbpass);if(!$conn){die('连接失败:'.mysqli_error($conn));}//设置编码，防止中文乱码mysqli_query($conn,"set names utf8");$sql='SELECT runoob_id, runoob_title, 
        runoob_author, submission_date
        FROM runoob_tbl';mysqli_select_db($conn,'RUNOOB');$retval=mysqli_query($conn,$sql);if(!$retval){die('无法读取数据:'.mysqli_error($conn));}echo'<h2>菜鸟教程 mysqli_fetch_array 测试</h2>';echo'<table border="1"><tr><td>教程 ID</td><td>标题</td><td>作者</td><td>提交日期</td></tr>';while($row=mysqli_fetch_array($retval,MYSQLI_ASSOC)){echo"<tr><td>{$row['runoob_id']}</td>"."<td>{$row['runoob_title']}</td>"."<td>{$row['runoob_author']}</td>"."<td>{$row['submission_date']}</td>"."</tr>";}echo'</table>';mysqli_close($conn);?>输出结果如下所示：以上实例中，读取的每行记录赋值给变量 $row，然后再打印出每个值。注意：记住如果你需要在字符串中使用变量，请将变量置于花括号。在上面的例子中，PHP mysqli_fetch_array() 函数第二个参数为MYSQLI_ASSOC，

设置该参数查询结果返回关联数组，你可以使用字段名称来作为数组的索引。PHP 提供了另外一个函数mysqli_fetch_assoc(), 该函数从结果集中取得一行作为关联数组。
返回根据从结果集取得的行生成的关联数组，如果没有更多行，则返回 false。实例尝试以下实例，该实例使用了mysqli_fetch_assoc()函数来输出数据表 runoob_tbl 的所有记录：使用 mysqli_fetch_assoc 获取数据：<?php$dbhost='localhost:3306';//mysql服务器主机地址$dbuser='root';//mysql用户名$dbpass='123456';//mysql用户名密码$conn=mysqli_connect($dbhost,$dbuser,$dbpass);if(!$conn){die('连接失败:'.mysqli_error($conn));}//设置编码，防止中文乱码mysqli_query($conn,"set names utf8");$sql='SELECT runoob_id, runoob_title, 
        runoob_author, submission_date
        FROM runoob_tbl';mysqli_select_db($conn,'RUNOOB');$retval=mysqli_query($conn,$sql);if(!$retval){die('无法读取数据:'.mysqli_error($conn));}echo'<h2>菜鸟教程 mysqli_fetch_assoc 测试</h2>';echo'<table border="1"><tr><td>教程 ID</td><td>标题</td><td>作者</td><td>提交日期</td></tr>';while($row=mysqli_fetch_assoc($retval)){echo"<tr><td>{$row['runoob_id']}</td>"."<td>{$row['runoob_title']}</td>"."<td>{$row['runoob_author']}</td>"."<td>{$row['submission_date']}</td>"."</tr>";}echo'</table>';mysqli_close($conn);?>输出结果如下所示：你也可以使用常量 MYSQLI_NUM 作为 PHP mysqli_fetch_array() 函数的第二个参数，返回数字数组。实例以下实例使用MYSQLI_NUM参数显示数据表 runoob_tbl 的所有记录:使用 mysqli_fetch_array MYSQLI_NUM 参数获取数据：<?php$dbhost='localhost:3306';//mysql服务器主机地址$dbuser='root';//mysql用户名$dbpass='123456';//mysql用户名密码$conn=mysqli_connect($dbhost,$dbuser,$dbpass);if(!$conn){die('连接失败:'.mysqli_error($conn));}//设置编码，防止中文乱码mysqli_query($conn,"set names utf8");$sql='SELECT runoob_id, runoob_title, 
        runoob_author, submission_date
        FROM runoob_tbl';mysqli_select_db($conn,'RUNOOB');$retval=mysqli_query($conn,$sql);if(!$retval){die('无法读取数据:'.mysqli_error($conn));}echo'<h2>菜鸟教程 mysqli_fetch_array 测试</h2>';echo'<table border="1"><tr><td>教程 ID</td><td>标题</td><td>作者</td><td>提交日期</td></tr>';while($row=mysqli_fetch_array($retval,MYSQLI_NUM)){echo"<tr><td>{$row[0]}</td>"."<td>{$row[1]}</td>"."<td>{$row[2]}</td>"."<td>{$row[3]}</td>"."</tr>";}echo'</table>';mysqli_close($conn);?>输出结果如下所示：以上三个实例输出结果都一样。内存释放在我们执行完 SELECT 语句后，释放游标内存是一个很好的习惯。可以通过 PHP 函数 mysqli_free_result() 来实现内存的释放。以下实例演示了该函数的使用方法。实例尝试以下实例:使用 mysqli_free_result 释放内存：<?php$dbhost='localhost:3306';//mysql服务器主机地址$dbuser='root';//mysql用户名$dbpass='123456';//mysql用户名密码$conn=mysqli_connect($dbhost,$dbuser,$dbpass);if(!$conn){die('连接失败:'.mysqli_error($conn));}//设置编码，防止中文乱码mysqli_query($conn,"set names utf8");$sql='SELECT runoob_id, runoob_title, 
        runoob_author, submission_date
        FROM runoob_tbl';mysqli_select_db($conn,'RUNOOB');$retval=mysqli_query($conn,$sql);if(!$retval){die('无法读取数据:'.mysqli_error($conn));}echo'<h2>菜鸟教程 mysqli_fetch_array 测试</h2>';echo'<table border="1"><tr><td>教程 ID</td><td>标题</td><td>作者</td><td>提交日期</td></tr>';while($row=mysqli_fetch_array($retval,MYSQLI_NUM)){echo"<tr><td>{$row[0]}</td>"."<td>{$row[1]}</td>"."<td>{$row[2]}</td>"."<td>{$row[3]}</td>"."</tr>";}echo'</table>';//释放内存mysqli_free_result($retval);mysqli_close($conn);?>输出结果如下所示：


## 使用 mysqli_fetch_array MYSQLI_ASSOC 参数获取数据：


输出结果如下所示：


以上实例中，读取的每行记录赋值给变量 $row，然后再打印出每个值。


注意：记住如果你需要在字符串中使用变量，请将变量置于花括号。

**注意：**

在上面的例子中，PHP mysqli_fetch_array() 函数第二个参数为MYSQLI_ASSOC，

设置该参数查询结果返回关联数组，你可以使用字段名称来作为数组的索引。

**MYSQLI_ASSOC**

PHP 提供了另外一个函数mysqli_fetch_assoc(), 该函数从结果集中取得一行作为关联数组。
返回根据从结果集取得的行生成的关联数组，如果没有更多行，则返回 false。

**mysqli_fetch_assoc()**

尝试以下实例，该实例使用了mysqli_fetch_assoc()函数来输出数据表 runoob_tbl 的所有记录：


## 使用 mysqli_fetch_assoc 获取数据：


你也可以使用常量 MYSQLI_NUM 作为 PHP mysqli_fetch_array() 函数的第二个参数，返回数字数组。


以下实例使用MYSQLI_NUM参数显示数据表 runoob_tbl 的所有记录:

**MYSQLI_NUM**

## 使用 mysqli_fetch_array MYSQLI_NUM 参数获取数据：


以上三个实例输出结果都一样。


## 内存释放


在我们执行完 SELECT 语句后，释放游标内存是一个很好的习惯。


可以通过 PHP 函数 mysqli_free_result() 来实现内存的释放。


以下实例演示了该函数的使用方法。


尝试以下实例:


## 使用 mysqli_free_result 释放内存：

