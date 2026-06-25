# Java概述

> 来源: https://www.runoob.com/java/java-tutorial.html
> 爬取时间: 2026-06-25 13:27:15
> 学科: java | 难度: 基础
> 标签: Java, 入门, JVM, 基础

---


# Java 教程


Java 是由 Sun Microsystems 公司于 1995 年 5 月推出的高级程序设计语言。


Java 可运行于多个平台，如 Windows, Mac OS 及其他多种 UNIX 版本的系统。


本教程通过简单的实例将让大家更好的了解 Java 编程语言。


移动操作系统 Android 大部分的代码采用 Java 编程语言编程。


Java 在线工具

**Java 在线工具**

JDK 11 在线中文手册

**JDK 11 在线中文手册**

## 我的第一个 JAVA 程序


以下我们通过一个简单的实例来展示 Java 编程，创建文件HelloWorld.java(文件名需与类名一致), 代码如下：

**HelloWorld.java(文件名需与类名一致)**

## 实例


注：String args[]与String[] args都可以执行，但推荐使用String[] args，这样可以避免歧义和误读。

**注：**

运行以上实例，输出结果如下：


```
$ javac HelloWorld.java
$ java HelloWorld
Hello World
```


### 执行命令解析：


以上我们使用了两个命令javac和java。

**javac**
**java**

javac后面跟着的是java文件的文件名，例如 HelloWorld.java。
该命令用于将 java 源文件编译为 class 字节码文件，如：javac HelloWorld.java。

**javac HelloWorld.java**

运行javac命令后，如果成功编译没有错误的话，会出现一个 HelloWorld.class 的文件。


java后面跟着的是java文件中的类名,例如 HelloWorld 就是类名，如: java HelloWorld。


注意：java命令后面不要加.class。

**注意**

Gif 图演示：

