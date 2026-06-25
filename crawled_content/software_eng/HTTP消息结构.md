# HTTP消息结构

> 来源: https://www.runoob.com/http/http-messages.html
> 爬取时间: 2026-06-25 13:29:30
> 学科: software_eng | 难度: 基础
> 标签: 计算机网络, HTTP, 请求, 响应, 基础

---


# HTTP 消息结构


HTTP 是基于客户端/服务端（C/S）的架构模型，通过一个可靠的链接来交换信息，是一个无状态的请求/响应协议。


HTTP 消息是客户端和服务器之间通信的基础，它们由一系列的文本行组成，遵循特定的格式和结构。


HTTP消息分为两种类型：请求消息和响应消息。


一个 HTTP 客户端是一个应用程序（Web 浏览器或其他任何客户端），通过连接到服务器达到向服务器发送一个或多个 HTTP 的请求的目的。


一个 HTTP 服务器 同样也是一个应用程序（通常是一个 Web 服务，如 Nginx、Apache 服务器或 IIS 服务器等），通过接收客户端的请求并向客户端发送 HTTP 响应数据。


## 客户端请求消息


客户端发送一个HTTP请求到服务器的请求消息包括以下格式：请求行（request line）、请求头部（header）、空行和请求数据四个部分组成，下图给出了请求报文的一般格式。

- 请求行（Request Line）：方法：如 GET、POST、PUT、DELETE等，指定要执行的操作。请求 URI（统一资源标识符）：请求的资源路径，通常包括主机名、端口号（如果非默认）、路径和查询字符串。HTTP 版本：如 HTTP/1.1 或 HTTP/2。请求行的格式示例：GET /index.html HTTP/1.1

请求行（Request Line）：

**请求行**
- 方法：如 GET、POST、PUT、DELETE等，指定要执行的操作。
**方法**
- 请求 URI（统一资源标识符）：请求的资源路径，通常包括主机名、端口号（如果非默认）、路径和查询字符串。
**请求 URI**
- HTTP 版本：如 HTTP/1.1 或 HTTP/2。
**HTTP 版本**

请求行的格式示例：GET /index.html HTTP/1.1

`GET /index.html HTTP/1.1`
- 请求头（Request Headers）：包含了客户端环境信息、请求体的大小（如果有）、客户端支持的压缩类型等。常见的请求头包括Host、User-Agent、Accept、Accept-Encoding、Content-Length等。

请求头（Request Headers）：

**请求头**
- 包含了客户端环境信息、请求体的大小（如果有）、客户端支持的压缩类型等。
- 常见的请求头包括Host、User-Agent、Accept、Accept-Encoding、Content-Length等。
`Host`
`User-Agent`
`Accept`
`Accept-Encoding`
`Content-Length`
- 空行：请求头和请求体之间的分隔符，表示请求头的结束。

空行：

**空行**
- 请求头和请求体之间的分隔符，表示请求头的结束。
- 请求体（可选）：在某些类型的HTTP请求（如 POST 和 PUT）中，请求体包含要发送给服务器的数据。

请求体（可选）：

**请求体**
- 在某些类型的HTTP请求（如 POST 和 PUT）中，请求体包含要发送给服务器的数据。

## 服务器响应消息


HTTP 响应也由四个部分组成，分别是：状态行、消息报头、空行和响应正文。

- 状态行（Status Line）：HTTP 版本：与请求消息中的版本相匹配。状态码：三位数，表示请求的处理结果，如 200 表示成功，404 表示未找到资源。状态信息：状态码的简短描述。状态行的格式示例：HTTP/1.1 200 OK

状态行（Status Line）：

**状态行**
- HTTP 版本：与请求消息中的版本相匹配。
- 状态码：三位数，表示请求的处理结果，如 200 表示成功，404 表示未找到资源。
**状态码**
- 状态信息：状态码的简短描述。
**状态信息**

状态行的格式示例：HTTP/1.1 200 OK

`HTTP/1.1 200 OK`
- 响应头（Response Headers）：包含了服务器环境信息、响应体的大小、服务器支持的压缩类型等。常见的响应头包括Content-Type、Content-Length、Server、Set-Cookie等。

响应头（Response Headers）：

**响应头**
- 包含了服务器环境信息、响应体的大小、服务器支持的压缩类型等。
- 常见的响应头包括Content-Type、Content-Length、Server、Set-Cookie等。
`Content-Type`
`Server`
`Set-Cookie`
- 空行：响应头和响应体之间的分隔符，表示响应头的结束。
- 响应头和响应体之间的分隔符，表示响应头的结束。
- 响应体（可选）：包含服务器返回的数据，如请求的网页内容、图片、JSON数据等。

响应体（可选）：

**响应体**
- 包含服务器返回的数据，如请求的网页内容、图片、JSON数据等。

## 实例


下面实例是一点典型的使用 GET 来传递数据的实例：


客户端请求：


```
GET /index.html HTTP/1.1
Host: www.example.com
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8
Accept-Encoding: gzip, deflate
Connection: keep-alive
```


服务端响应:


```
HTTP/1.1 200 OK
Date: Wed, 18 Apr 2024 12:00:00 GMT
Server: Apache/2.4.1 (Unix)
Last-Modified: Wed, 18 Apr 2024 11:00:00 GMT
Content-Length: 12345
Content-Type: text/html; charset=UTF-8

<!DOCTYPE html>
<html>
<head>
    <title>Example Page</title>
</head>
<body>
    <h1>Hello, World!</h1>
    <!-- The rest of the HTML content -->
</body>
</html>
```


在实际应用中，HTTP 消息可以包含更多的头字段，并且请求体和响应体的大小会根据传输的数据而变化。

