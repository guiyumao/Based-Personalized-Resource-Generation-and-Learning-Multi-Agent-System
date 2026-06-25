# 文件IO

> 来源: https://www.runoob.com/java/java-files-io.html
> 爬取时间: 2026-06-25 13:27:36
> 学科: java | 难度: 基础
> 标签: Java, 文件IO, 基础

---


# Java 流(Stream)、文件(File)和IO


Java 中的流（Stream）、文件（File）和 IO（输入输出）是处理数据读取和写入的基础设施，它们允许程序与外部数据（如文件、网络、系统输入等）进行交互。


java.io 包是 Java 标准库中的一个核心包，提供了用于系统输入和输出的类，它包含了处理数据流（字节流和字符流）、文件读写、序列化以及数据格式化的工具。


java.io 是处理文件操作、流操作以及低级别 IO 操作的基础包。


java.io 包中的流支持很多种格式，比如：基本类型、对象、本地化字符集等等。


一个流可以理解为一个数据的序列。输入流表示从一个源读取数据，输出流表示向一个目标写数据。


## 读取控制台输入


Java 的控制台输入由 System.in 完成。


为了获得一个绑定到控制台的字符流，你可以把 System.in 包装在一个 BufferedReader 对象中来创建一个字符流。


下面是创建 BufferedReader 的基本语法：


BufferedReader 对象创建后，我们便可以使用 read() 方法从控制台读取一个字符，或者用 readLine() 方法读取一个字符串。


## 从控制台读取多字符输入


从 BufferedReader 对象读取一个字符要使用 read() 方法，它的语法如下：


每次调用 read() 方法，它从输入流读取一个字符并把该字符作为整数值返回。 当流结束的时候返回 -1。该方法抛出 IOException。


下面的程序示范了用 read() 方法从控制台不断读取字符直到用户输入q。


## BRRead.java 文件代码：


以上实例编译运行结果如下:


```
输入字符, 按下 'q' 键退出。
runoob
r
u
n
o
o
b


q
q
```


## 从控制台读取字符串


从标准输入读取一个字符串需要使用 BufferedReader 的 readLine() 方法。


它的一般格式是：


下面的程序读取和显示字符行直到你输入了单词"end"。


## BRReadLines.java 文件代码：


```
Enter lines of text.
Enter 'end' to quit.
This is line one
This is line one
This is line two
This is line two
end
end
```


JDK 5 后的版本我们也可以使用Java Scanner类来获取控制台的输入。


## 控制台输出


在此前已经介绍过，控制台的输出由 print( ) 和 println() 完成。这些方法都由类 PrintStream 定义，System.out 是该类对象的一个引用。


PrintStream 继承了 OutputStream类，并且实现了方法 write()。这样，write() 也可以用来往控制台写操作。


PrintStream 定义 write() 的最简单格式如下所示：


该方法将 byteval 的低八位字节写到流中。


### 实例


下面的例子用 write() 把字符 "A" 和紧跟着的换行符输出到屏幕：


## WriteDemo.java 文件代码：


运行以上实例在输出窗口输出 "A" 字符


```
A
```


注意：write() 方法不经常使用，因为 print() 和 println() 方法用起来更为方便。

**注意：**

## 读写文件


如前所述，一个流被定义为一个数据序列。输入流用于从源读取数据，输出流用于向目标写数据。


下图是一个描述输入流和输出流的类层次图。


### 字节流（处理二进制数据）


字节流用于处理二进制数据，例如文件、图像、视频等。

`InputStream`
`OutputStream`
`FileInputStream`
`FileOutputStream`
`BufferedInputStream`
`BufferedOutputStream`
`ByteArrayInputStream`
`ByteArrayOutputStream`
`DataInputStream`
`int`
`float`
`boolean`
`DataOutputStream`
`ObjectInputStream`
`ObjectOutputStream`
`PipedInputStream`
`PipedOutputStream`
`FilterInputStream`
`FilterOutputStream`
`SequenceInputStream`

### 字符流（处理文本数据）


字符流用于处理文本数据，例如读取和写入字符串或文件。

`Reader`
`Writer`
`FileReader`
`FileWriter`
`BufferedReader`
`BufferedWriter`
`CharArrayReader`
`CharArrayWriter`
`StringReader`
`StringWriter`
`PrintWriter`
`PipedReader`
`PipedWriter`
`LineNumberReader`
`PushbackReader`

### 辅助类（其他重要类）


辅助类提供对文件、目录以及随机文件访问的支持。

`File`
`RandomAccessFile`
`Console`

下面将要讨论的两个重要的流是FileInputStream和FileOutputStream。

**FileInputStream**
**FileOutputStream**

## FileInputStream


该流用于从文件读取数据，它的对象可以用关键字 new 来创建。


有多种构造方法可用来创建对象。


可以使用字符串类型的文件名来创建一个输入流对象来读取文件：


也可以使用一个文件对象来创建一个输入流对象来读取文件。我们首先得使用 File() 方法来创建一个文件对象：


创建了 InputStream 对象，就可以使用下面的方法来读取流或者进行其他的流操作。

`int read()`
`int data = inputStream.read();`
`int read(byte[] b)`
`b`
`byte[] buffer = new byte[1024]; int bytesRead = inputStream.read(buffer);`
`int read(byte[] b, int off, int len)`
`len`
`off`
`byte[] buffer = new byte[1024]; int bytesRead = inputStream.read(buffer, 0, buffer.length);`
`long skip(long n)`
`n`
`long skippedBytes = inputStream.skip(100);`
`int available()`
`int availableBytes = inputStream.available();`
`void close()`
`inputStream.close();`
`void mark(int readlimit)`
`readlimit`
`inputStream.mark(1024);`
`void reset()`
`IOException`
`inputStream.reset();`
`boolean markSupported()`
`mark()`
`reset()`
`boolean isMarkSupported = inputStream.markSupported();`

除了 InputStream 外，还有一些其他的输入流，更多的细节参考下面链接：

- ByteArrayInputStream
- DataInputStream

## FileOutputStream


该类用来创建一个文件并向文件中写数据。


如果该流在打开文件进行输出前，目标文件不存在，那么该流会创建该文件。


有两个构造方法可以用来创建 FileOutputStream 对象。


使用字符串类型的文件名来创建一个输出流对象：


也可以使用一个文件对象来创建一个输出流来写文件。我们首先得使用File()方法来创建一个文件对象：


创建 OutputStream 对象完成后，就可以使用下面的方法来写入流或者进行其他的流操作。

`void write(int b)`
`outputStream.write(255);`
`void write(byte[] b)`
`byte[] data = "Hello".getBytes(); outputStream.write(data);`
`void write(byte[] b, int off, int len)`
`byte[] data = "Hello".getBytes(); outputStream.write(data, 0, data.length);`
`void flush()`
`outputStream.flush();`
`outputStream.close();`

除了 OutputStream 外，还有一些其他的输出流，更多的细节参考下面链接：

- ByteArrayOutputStream
- DataOutputStream

下面是一个演示 InputStream 和 OutputStream 用法的例子：


## fileStreamTest.java 文件代码：


上面的程序首先创建文件test.txt，并把给定的数字以二进制形式写进该文件，同时输出到控制台上。


以上代码由于是二进制写入，可能存在乱码，你可以使用以下代码实例来解决乱码问题：


## fileStreamTest2.java 文件代码：


## 文件和I/O


还有一些关于文件和I/O的类，我们也需要知道：

- File Class(类)
- FileReader Class(类)
- FileWriter Class(类)

## Java中的目录


### 创建目录：


File类中有两个方法可以用来创建文件夹：

- mkdir( )方法创建一个文件夹，成功则返回true，失败则返回false。失败表明File对象指定的路径已经存在，或者由于整个路径还不存在，该文件夹不能被创建。
**mkdir( )**
- mkdirs()方法创建一个文件夹和它的所有父文件夹。
**mkdirs()**

下面的例子创建 "/tmp/user/java/bin"文件夹：


## CreateDir.java 文件代码：


编译并执行上面代码来创建目录 "/tmp/user/java/bin"。


注意：Java 在 UNIX 和 Windows 自动按约定分辨文件路径分隔符。如果你在 Windows 版本的 Java 中使用分隔符 (/) ，路径依然能够被正确解析。


## 读取目录


一个目录其实就是一个 File 对象，它包含其他文件和文件夹。


如果创建一个 File 对象并且它是一个目录，那么调用 isDirectory() 方法会返回 true。


可以通过调用该对象上的 list() 方法，来提取它包含的文件和文件夹的列表。


下面展示的例子说明如何使用 list() 方法来检查一个文件夹中包含的内容：


## DirList.java 文件代码：


以上实例编译运行结果如下：


```
目录 /tmp
bin 是一个目录
lib 是一个目录
demo 是一个目录
test.txt 是一个文件
README 是一个文件
index.html 是一个文件
include 是一个目录
```


## 删除目录或文件


删除文件可以使用java.io.File.delete()方法。

**java.io.File.delete()**

以下代码会删除目录/tmp/java/，需要注意的是当删除某一目录时，必须保证该目录下没有其他文件才能正确删除，否则将删除失败。

**/tmp/java/**

测试目录结构：


```
/tmp/java/
|-- 1.log
|-- test
```


## DeleteFileDemo.java 文件代码：

